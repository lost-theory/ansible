#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2013, Chris Hoffman <christopher.hoffman@gmail.com>
#
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
module: npm
short_description: Manage node.js packages with npm
description:
  - Manage node.js packages with Node Package Manager (npm)
version_added: 1.2
author: Chris Hoffman
options:
  name:
    description:
      - The name of a node.js library to install
    requires: false
    default: null
  path:
    description:
      - The base path where to install the node.js libraries
    required: false
    default: null
  version:
    description:
      - The version to be installed
    required: false
    default: null
  global:
    descrition:
      - Install the node.js library globally
    required: false
    default: no
    choices: [ "yes", "no" ]
  executable:
    description:
      - The executable location for npm.
      - This is useful if you are using a version manager, such as nvm
    required: false
    default: nvm
  production:
    description:
      - Install dependencies in production mode, excluding devDependencies
    required: false
    default: no
  state:
    description:
      - The state of the node.js library
    required: false
    default: present
    choices: [ "present", "absent", "latest" ]
examples:
   - code: "npm: name=coffee-script path=/app/location"
     description: Install I(coffee-script) node.js package.
   - code: "npm: name=coffee-script version=1.6.1 path=/app/location"
     description: Install I(coffee-script) node.js package on version 1.6.1.
   - code: "npm: name=coffee-script global=yes"
     description: Install I(coffee-script) node.js package globally.
   - code: "npm: name=coffee-script global=yes state=absent"
     description: Remove the globally package I(coffee-script).
   - code: "npm: path=/app/location"
     description: Install packages based on package.json.
   - code: "npm: path=/app/location state=latest"
     description: Update packages based on package.json to their latest version.
   - code: "npm: path=/app/location executable=/opt/nvm/v0.10.1/bin/npm state=present"
     description: Install packages based on package.json using the npm installed with nvm v0.10.1.
'''

import os

try:
    import json
except ImportError:
    import simplejson as json

class Npm(object):
    def __init__(self, module, **kwargs):
        self.module = module
        self.glbl = kwargs['glbl']
        self.name = kwargs['name']
        self.version = kwargs['version']
        self.path = kwargs['path']
        self.production = kwargs['production']
        
        if kwargs['executable']:
            self.executable = kwargs['executable']
        else:
            self.executable = module.get_bin_path('npm', True)

        if kwargs['version']:
            self.name_version = self.name + '@' + self.version
        else:
            self.name_version = self.name

    def _exec(self, args, run_in_check_mode=False, check_rc=True):
        if not self.module.check_mode or (self.module.check_mode and run_in_check_mode):
            cmd = [self.executable] + args

            if self.glbl:
                cmd.append('--global')
            if self.production:
                cmd.append('--production')                
            if self.name:
                cmd.append(self.name_version)

            #If path is specified, cd into that path and run the command.
            if self.path:
                os.chdir(self.path)

            rc, out, err = self.module.run_command(cmd, check_rc=check_rc)
            return out
        return ''

    def list(self):
        cmd = ['list', '--json']

        installed = list()
        missing = list()
        data = json.loads(self._exec(cmd, True, False))
        if 'dependencies' in data:
            for dep in data['dependencies']:
                if 'missing' in data['dependencies'][dep] and data['dependencies'][dep]['missing']:
                    missing.append(dep)
                else:
                    installed.append(dep)
        #Named dependency not installed
        else:
            missing.append(self.name)

        return installed, missing

    def install(self):
        return self._exec(['install'])

    def update(self):
        return self._exec(['update'])

    def uninstall(self):
        return self._exec(['uninstall'])

    def list_outdated(self):
        outdated = list()
        data = self._exec(['outdated'], True, False)
        for dep in data.splitlines():
            if dep:
                pkg, other = dep.split('@', 1)
                outdated.append(pkg)

        return outdated


def main(**params):
    arg_spec = dict(
        name=dict(default=None),
        path=dict(default=None),
        version=dict(default=None),
        production=dict(default='no', type='bool'),
        executable=dict(default=None),
        state=dict(default='present', choices=['present', 'absent', 'latest'])
    )
    arg_spec['global']=dict(default='no', type='bool')
    module = AnsibleModule(params=params,
        argument_spec=arg_spec,
        supports_check_mode=True
    )

    name = module.params['name']
    path = module.params['path']
    version = module.params['version']
    glbl = module.params['global']
    production = module.params['production']
    executable = module.params['executable']
    state = module.params['state']

    if not path and not glbl:
        module.fail_json(msg='path must be specified when not using global')
    if state == 'absent' and not name:
        module.fail_json(msg='uninstalling a package is only available for named packages')

    npm = Npm(module, name=name, path=path, version=version, glbl=glbl, production=production, \
              executable=executable)

    changed = False
    if state == 'present':
        installed, missing = npm.list()
        if len(missing):
            changed = True
            npm.install()
    elif state == 'latest':
        installed, missing = npm.list()
        outdated = npm.list_outdated()
        if len(missing) or len(outdated):
            changed = True
            npm.install()
            npm.update()
    else: #absent
        installed, missing = npm.list()
        if name in installed:
            changed = True
            npm.uninstall()

    return module.exit_json(changed=changed)

# this is magic, see lib/ansible/module_common.py

from newcommon import *

