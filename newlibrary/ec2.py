#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: ec2
short_description: create an instance in ec2, return instanceid
description:
     - creates ec2 instances and optionally waits for it to be 'running'. This module has a dependency on python-boto.
version_added: "0.9"
options:
  key_name:
    description:
      - key pair to use on the instance
    required: true
    default: null
    aliases: ['keypair']
  id:
    description:
      - identifier for this instance or set of instances, so that the module will be idempotent with respect to EC2 instances.
    required: false
    default: null
    aliases: []
  group:
    description:
      - security group to use with the instance
    required: false
    default: null 
    aliases: []
  group_id:
    version_added: "1.1"
    description:
      - security group id to use with the instance 
    required: false
    default: null
    aliases: []
  instance_type:
    description:
      - instance type to use for the instance
    required: true
    default: null
    aliases: []
  image:
    description:
       - I(emi) (or I(ami)) to use for the instance
    required: true
    default: null
    aliases: []
  kernel:
    description:
      - kernel I(eki) to use for the instance
    required: false
    default: null
    aliases: []
  ramdisk:
    description:
      - ramdisk I(eri) to use for the instance
    required: false
    default: null
    aliases: []
  wait:
    description:
      - wait for the instance to be in state 'running' before returning
    required: false
    default: "no"
    choices: [ "yes", "no" ]
    aliases: []
  wait_timeout:
    description:
      - how long before wait gives up, in seconds
    default: 300
    aliases: []
  ec2_url:
    description:
      - url to use to connect to EC2 or your Eucalyptus cloud (by default the module will use EC2 endpoints)
    required: false
    default: null
    aliases: []
  ec2_secret_key:
    description:
      - ec2 secret key
    required: false
    default: null
    aliases: []
  ec2_access_key:
    description:
      - ec2 access key
    required: false
    default: null
    aliases: []
  count:
    description:
      - number of instances to launch
    required: False
    default: 1
    aliases: []
  monitor:
    version_added: "1.1"
    description:
      - enable detailed monitoring (CloudWatch) for instance
    required: false
    default: null
    aliases: []
  user_data:
    version_added: "0.9"
    description:
      - opaque blob of data which is made available to the ec2 instance
    required: false
    default: null
    aliases: []
  instance_tags:
    version_added: "1.0"
    description:
      - a hash/dictionary of tags to add to the new instance; '{"key":"value"}' and '{"key":"value","key":"value"}'
    required: false
    default: null
    aliases: []
  vpc_subnet_id:
    version_added: "1.1"
    description:
      - the subnet ID in which to launch the instance (VPC)
    required: false
    default: null
    aliases: []
examples:
   - code: 'local_action: ec2 keypair=admin instance_type=m1.large image=emi-40603AD1 wait=yes group=webserver count=3 group=webservers'
     description: "Examples from Ansible Playbooks"
requirements: [ "boto" ]
author: Seth Vidal, Tim Gerla, Lester Wade
'''

import sys
import time

try:
    import boto
except ImportError:
    print "failed=True msg='boto required for this module'"
    raise Exception('was going to call sys.exit(1)') #XXX

def main(**params):
    module = AnsibleModule(params=params,
        argument_spec = dict(
            key_name = dict(required=True, aliases = ['keypair']),
            id = dict(),
            group = dict(),
            group_id = dict(),
            instance_type = dict(aliases=['type']),
            image = dict(required=True),
            kernel = dict(),
            count = dict(default='1'), 
            monitoring = dict(choices=BOOLEANS, default=False),
            ramdisk = dict(),
            wait = dict(choices=BOOLEANS, default=False),
            wait_timeout = dict(default=300),
            ec2_url = dict(aliases=['EC2_URL']),
            ec2_secret_key = dict(aliases=['EC2_SECRET_KEY'], no_log=True),
            ec2_access_key = dict(aliases=['EC2_ACCESS_KEY']),
            user_data = dict(),
            instance_tags = dict(),
            vpc_subnet_id = dict(),
        )
    )

    key_name = module.params.get('key_name')
    id = module.params.get('id')
    group_name = module.params.get('group')
    group_id = module.params.get('group_id')
    instance_type = module.params.get('instance_type')
    image = module.params.get('image')
    count = module.params.get('count') 
    monitoring = module.params.get('monitoring')
    kernel = module.params.get('kernel')
    ramdisk = module.params.get('ramdisk')
    wait = module.params.get('wait')
    wait_timeout = int(module.params.get('wait_timeout'))
    ec2_url = module.params.get('ec2_url')
    ec2_secret_key = module.params.get('ec2_secret_key')
    ec2_access_key = module.params.get('ec2_access_key')
    user_data = module.params.get('user_data')
    instance_tags = module.params.get('instance_tags')
    vpc_subnet_id = module.params.get('vpc_subnet_id')

    # allow eucarc environment variables to be used if ansible vars aren't set
    if not ec2_url and 'EC2_URL' in os.environ:
        ec2_url = os.environ['EC2_URL']
    if not ec2_secret_key and 'EC2_SECRET_KEY' in os.environ:
        ec2_secret_key = os.environ['EC2_SECRET_KEY']
    if not ec2_access_key and 'EC2_ACCESS_KEY' in os.environ:
        ec2_access_key = os.environ['EC2_ACCESS_KEY']

    try:
        if ec2_url: # if we have an URL set, connect to the specified endpoint 
            ec2 = boto.connect_ec2_endpoint(ec2_url, ec2_access_key, ec2_secret_key)
        else: # otherwise it's Amazon.
            ec2 = boto.connect_ec2(ec2_access_key, ec2_secret_key)
    except boto.exception.NoAuthHandlerFound, e:
        module.fail_json(msg = str(e))
    
    # Here we try to lookup the group name from the security group id - if group_id is set.

    try:
        if group_id:
            grp_details = ec2.get_all_security_groups(group_ids=group_id)
            grp_item = grp_details[0]
            group_name = grp_item.name
    except boto.exception.NoAuthHandlerFound, e:
            module.fail_json(msg = str(e))

    # Lookup any instances that much our run id.
    
    running_instances = []
    count_remaining = int(count)
        
    if id != None:
        filter_dict = {'client-token':id, 'instance-state-name' : 'running'}
        previous_reservations = ec2.get_all_instances(None, filter_dict )
        for res in previous_reservations:
            for prev_instance in res.instances:
                running_instances.append(prev_instance)
        count_remaining = count_remaining - len(running_instances) 
#        module.fail_json(msg = "known running instances: %s" % (running_instances)) 

    
    # Both min_count and max_count equal count parameter. This means the launch request is explicit (we want count, or fail) in how many instances we want.

    
    if count_remaining > 0:
        try:
            res = ec2.run_instances(image, key_name = key_name,
                                client_token=id,
                                min_count = count_remaining, 
                                max_count = count_remaining,
                                monitoring_enabled = monitoring,
                                security_groups = [group_name],
                                instance_type = instance_type,
                                kernel_id = kernel,
                                ramdisk_id = ramdisk,
                                subnet_id = vpc_subnet_id,
                                user_data = user_data)
        except boto.exception.BotoServerError, e:
            module.fail_json(msg = "%s: %s" % (e.error_code, e.error_message))

        instids = [ i.id for i in res.instances ]
        while True:
            try:
                res.connection.get_all_instances(instids)
                break
            except boto.exception.EC2ResponseError as e:
                if "<Code>InvalidInstanceID.NotFound</Code>" in str(e):
                    # there's a race between start and get an instance
                    continue
                else:
                    module.fail_json(msg = str(e))

        if instance_tags:
            try:
                ec2.create_tags(instids, module.from_json(instance_tags))
            except boto.exception.EC2ResponseError as e:
                module.fail_json(msg = "%s: %s" % (e.error_code, e.error_message))

        # wait here until the instances are up
        res_list = res.connection.get_all_instances(instids)
        this_res = res_list[0]
        num_running = 0
        wait_timeout = time.time() + wait_timeout
        while wait and wait_timeout > time.time() and num_running < len(instids):
            res_list = res.connection.get_all_instances(instids)
            this_res = res_list[0]
            num_running = len([ i for i in this_res.instances if i.state=='running' ])
            time.sleep(5)
        if wait and wait_timeout <= time.time():
            # waiting took too long
            module.fail_json(msg = "wait for instances running timeout on %s" % time.asctime())
    
        for inst in this_res.instances:
            running_instances.append(inst)
        
    instance_dict_array = []
    for inst in running_instances:
        d = {
           'id': inst.id,
           'ami_launch_index': inst.ami_launch_index,
           'private_ip': inst.private_ip_address,
           'private_dns_name': inst.private_dns_name,
           'public_ip': inst.ip_address,
           'dns_name': inst.dns_name,
           'public_dns_name': inst.public_dns_name,
           'state_code': inst.state_code,
           'architecture': inst.architecture,
           'image_id': inst.image_id,
           'key_name': inst.key_name,
           'virtualization_type': inst.virtualization_type,
           'placement': inst.placement,
           'kernel': inst.kernel,
           'ramdisk': inst.ramdisk,
           'launch_time': inst.launch_time,
           'instance_type': inst.instance_type,
           'root_device_type': inst.root_device_type,
           'root_device_name': inst.root_device_name,
           'state': inst.state,
           'hypervisor': inst.hypervisor
            }
        instance_dict_array.append(d)

    return module.exit_json(changed=True, instances=instance_dict_array)

# this is magic, see lib/ansible/module_common.py

from newcommon import *


