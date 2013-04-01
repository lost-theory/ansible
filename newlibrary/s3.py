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
module: s3
short_description: idempotent s3 module putting a file into S3. 
description:
    - This module allows the user to dictate the presence of a given file in an S3 bucket. If or once the key (file) exists in the bucket, it returns a time-expired download url. This module has a dependency on python-boto.
version_added: "1.1"
options:
  bucket:
    description:
      - bucket you wish to present/absent for the key (file in path).
    required: true
    default: null 
    aliases: []
  state:
    description:
      - desired state for both bucket and file. 
    default: null
    aliases: []
  path:
    description:
      - path to the key (file) which you wish to be present/absent in the bucket.
    required: false
    default: null
    aliases: []
  expiry:
    description:
      - expiry period (in seconds) for returned download URL.
    required: false
    default: 600
    aliases: []
examples:
   - code: 's3 bucket=mybucket path=/path/to/file state=present'
     description: "Simple playbook example"
requirements: [ "boto" ]
author: Lester Wade
'''

import sys
import os
import urlparse

try:
    import boto
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)

def main(**params):
    module = AnsibleModule(params=params,
        argument_spec = dict(
            bucket = dict(),
            path = dict(),
            state  = dict(choices=['present', 'absent']),
            expiry = dict(default=600),
            s3_url = dict(aliases=['S3_URL']),
            ec2_secret_key = dict(aliases=['EC2_SECRET_KEY']),
            ec2_access_key = dict(aliases=['EC2_ACCESS_KEY']),
        ),
        required_together=[ ['bucket', 'path', 'state'] ],
    )

    bucket_name = module.params.get('bucket')
    path = os.path.expanduser(module.params['path'])
    state = module.params.get('state')
    expiry = int(module.params['expiry'])
    s3_url = module.params.get('s3_url')
    ec2_secret_key = module.params.get('ec2_secret_key')
    ec2_access_key = module.params.get('ec2_access_key')

    # allow eucarc environment variables to be used if ansible vars aren't set
    
    if not s3_url and 'S3_URL' in os.environ:
        s3_url = os.environ['S3_URL']
    if not ec2_secret_key and 'EC2_SECRET_KEY' in os.environ:
        ec2_secret_key = os.environ['EC2_SECRET_KEY']
    if not ec2_access_key and 'EC2_ACCESS_KEY' in os.environ:
        ec2_access_key = os.environ['EC2_ACCESS_KEY']

    # If we have an S3_URL env var set, this is likely to be Walrus, so change connection method
    if 'S3_URL' in os.environ:
        try:
            walrus = urlparse.urlparse(s3_url).hostname
            s3 = boto.connect_walrus(walrus, ec2_access_key, ec2_secret_key)
        except boto.exception.NoAuthHandlerFound, e:
            module.fail_json(msg = str(e))
    else:
        try:
            s3 = boto.connect_s3(ec2_access_key, ec2_secret_key)
        except boto.exception.NoAuthHandlerFound, e:
            module.fail_json(msg = str(e))
   
    # README - Future features this module should have:
    # enhanced path (contents of a directory)
    # md5sum check of file vs. key in bucket
    # a user-friendly way to fetch the key (maybe a "fetch" parameter option)
    # persistent download URL if desired
    
    # Lets get some information from the s3 connection, including bucket check ...
    bucket = s3.lookup(bucket_name)
    if bucket:
        bucket_exists = True
    else:
        bucket_exists = False
    
    # Lets list the contents
    if bucket_exists is True:
        bucket_contents = bucket.list()

    # Check filename is valid, if not downloading 
    if path: 
        if not os.path.exists(path):
            failed = True
            module.fail_json(msg="Source %s cannot be found" % (path), failed=failed)
            sys.exit(0)

    # Default to setting the key to the same as the filename if not downloading. Adding custom key would be trivial.
    key_name = os.path.basename(path)
   
    # Check to see if the key already exists 
    if bucket_exists is True:
        try:
            key_check = bucket.get_key(key_name)
            if key_check:
                key_exists = True
            else:
                key_exists = False
        except s3.provider.storage_response_error, e:
            module.fail_json(msg= str(e))

    if state == 'present':
        if bucket_exists is True and key_exists is True:
            exists = True
            changed = False
            return module.exit_json(msg="Bucket and key already exist", changed=changed)
            sys.exit(0)    

   # If bucket exists, there cannot be a key within, lets create it ...
    if state == 'present':
        if bucket_exists is False:
            try:
                bucket = s3.create_bucket(bucket_name)
                bucket_exists = True
                key_exists = False
                changed = True
            except s3.provider.storage_create_error, e:
                module.fail_json(msg = str(e))
    
    # TO-DO, md5sum of key and local file to be confident that its valid.
    # If bucket now exists but key doesn't, create the key
    if state == 'present':
        if bucket_exists is True and key_exists is False:
            try:
                key = bucket.new_key(key_name)  
                key.set_contents_from_filename(path)
                url = key.generate_url(expiry)
                return module.exit_json(msg="Put operation complete", url=url, changed=True)
                sys.exit(0)
            except s3.provider.storage_copy_error, e:
                module.fail_json(msg= str(e))

    # If state is absent and the bucket exists (doesn't matter about key since the bucket is the container), delete it.
    if state == 'absent':
        if bucket_exists is True:
            try:
                for contents in bucket.list():
                    bucket.delete_key(contents)
                    s3.delete_bucket(bucket)
                    changed = True
                    return module.exit_json(msg="Bucket and key removed.", changed=changed)
                    sys.exit(0)
            except s3.provider.storage_response_error, e:
                module.fail_json(msg= str(e))
        else:
            changed = False
            return module.exit_json(msg="Bucket and key do not exist", changed=changed)
    
    # TO DO - ADD BUCKET DOWNLOAD OPTION
    #    # If download is specified, fetch it
    #    if download:
    #        if bucket_exists is True and key_exists is True:
    #            try:
    #                getkey = bucket.lookup(key_name)
    #                getkey.get_contents_to_filename(path)
    #                url = getkey.generate_url(expiry)
    #                return module.exit_json(msg="GET operation complete", url=url, changed=True)
    #                sys.exit(0)
    #            except s3.provider.storage_copy_error, e:
    #                module.fail_json(msg= str(e))
    
    sys.exit(0)

# this is magic, see lib/ansible/module_common.py

from newcommon import *


