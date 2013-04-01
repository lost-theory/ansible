#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Flowroute LLC
# Written by Matthew Williams <matthew@flowroute.com>
# Based on yum module written by Seth Vidal <skvidal at fedoraproject.org>
#
# This module is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software.  If not, see <http://www.gnu.org/licenses/>.
#

DOCUMENTATION = '''
---
module: apt
short_description: Manages apt-packages
description:
  - Manages I(apt) packages (such as for Debian/Ubuntu).
version_added: "0.0.2"
options:
  pkg:
    description:
      - A package name or package specifier with version, like C(foo) or C(foo=1.0)
    required: true
    default: null
  state:
    description:
      - Indicates the desired package state
    required: false
    default: present
    choices: [ "latest", "absent", "present" ]
  update_cache:
    description:
      - Run the equivalent of C(apt-get update) before the operation. Can be run as part of the package installation or as a separate step
    required: false
    default: "no"
    choices: [ "yes", "no" ]
  purge:
    description:
     - Will force purging of configuration files if the module state is set to I(absent).
    required: false
    default: "no"
    choices: [ "yes", "no" ]
  default_release:
    description:
      - Corresponds to the C(-t) option for I(apt) and sets pin priorities
    required: false
    default: null
  install_recommends:
    description:
      - Corresponds to the C(--no-install-recommends) option for I(apt), default behavior works as apt's default behavior, C(no) does not install recommended packages. Suggested packages are never installed.
    required: false
    default: "yes"
    choices: [ "yes", "no" ]
  force:
    description:
      - If C(yes), force installs/removes.
    required: false
    default: "no"
    choices: [ "yes", "no" ]
  upgrade:
    description:
      - 'If yes, performs an apt-get upgrade. If dist, performs an apt-get dist-upgrade. Note: This does not upgrade a specific package, use state=latest for that.'
    version_added: "1.1"
    required: false
    default: no
    choices: [ "yes", "dist"]
author: Matthew Williams
notes: []
examples:
    - code: "apt: pkg=foo update_cache=yes"
      description: Update repositories cache and install C(foo) package
    - code: "apt: pkg=foo state=removed"
      description: Remove C(foo) package
    - code: "apt: pkg=foo state=installed"
      description: Install the package C(foo)
    - code: "apt: pkg=foo=1.00 state=installed"
      description: Install the version '1.00' of package C(foo)
    - code: "apt: pkg=nginx state=latest default_release=squeeze-backports update_cache=yes"
      description: Update the repository cache and update package C(ngnix) to latest version using default release C(squeeze-backport)
    - code: "apt: pkg=openjdk-6-jdk state=latest install_recommends=no"
      description: Install latest version of C(openjdk-6-jdk) ignoring C(install-reccomends)
    - code: "apt: upgrade=dist"
      description: Update all packages to the latest version
'''

import traceback
# added to stave off future warnings about apt api
import warnings
warnings.filterwarnings('ignore', "apt API not stable yet", FutureWarning)

# APT related constants
APT_PATH = "/usr/bin/apt-get"
APT = "DEBIAN_FRONTEND=noninteractive DEBIAN_PRIORITY=critical %s" % APT_PATH

def package_split(pkgspec):
    parts = pkgspec.split('=')
    if len(parts) > 1:
        return parts[0], parts[1]
    else:
        return parts[0], None

def package_status(m, pkgname, version, cache, state):
    try:
        pkg = cache[pkgname]
    except KeyError:
        if state == 'install':
            m.fail_json(msg="No package matching '%s' is available" % pkgname)
        else:
            return False, False
    if version:
        try :
            return pkg.is_installed and pkg.installed.version == version, False
        except AttributeError:
            #assume older version of python-apt is installed
            return pkg.isInstalled and pkg.installedVersion == version, False
    else:
        try :
            return pkg.is_installed, pkg.is_upgradable
        except AttributeError:
            #assume older version of python-apt is installed
            return pkg.isInstalled, pkg.isUpgradable

def install(m, pkgspec, cache, upgrade=False, default_release=None, install_recommends=True, force=False):
    packages = ""
    for package in pkgspec:
        name, version = package_split(package)
        installed, upgradable = package_status(m, name, version, cache, state='install')
        if not installed or (upgrade and upgradable):
            packages += "'%s' " % package

    if len(packages) != 0:
        if force:
            force_yes = '--force-yes'
        else:
            force_yes = ''

        cmd = "%s --option Dpkg::Options::=--force-confold -q -y %s install %s" % (APT, force_yes,packages)
        if default_release:
            cmd += " -t '%s'" % (default_release,)
        if not install_recommends:
            cmd += " --no-install-recommends"

        if m.check_mode:
            return m.exit_json(changed=True)

        rc, out, err = m.run_command(cmd)
        if rc:
            m.fail_json(msg="'apt-get install %s' failed: %s" % (packages, err))
        else:
            return m.exit_json(changed=True)
    else:
        return m.exit_json(changed=False)

def remove(m, pkgspec, cache, purge=False):
    packages = ""
    for package in pkgspec:
        name, version = package_split(package)
        installed, upgradable = package_status(m, name, version, cache, state='remove')
        if installed:
            packages += "'%s' " % package

    if len(packages) == 0:
        return m.exit_json(changed=False)
    else:
        purge = ''
        if purge:
            purge = '--purge'
        cmd = "%s -q -y %s remove %s" % (APT, purge,packages)

        if m.check_mode:
            return m.exit_json(changed=True)

        rc, out, err = m.run_command(cmd)
        if rc:
            m.fail_json(msg="'apt-get remove %s' failed: %s" % (packages, err))
        return m.exit_json(changed=True)

def upgrade(m, mode="yes"):
    upgrade_command = 'upgrade'
    if mode == "dist":
        upgrade_command = 'dist-upgrade'
    cmd = '%s -q -y -o "Dpkg::Options::=--force-confdef" -o "Dpkg::Options::=--force-confold" %s' % (APT, upgrade_command)
    rc, out, err = m.run_command(cmd)
    if rc:
        m.fail_json(msg="'apt-get %s' failed: %s" % (upgrade_command, err))
    if "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded." in out :
        return m.exit_json(changed=False)
    return m.exit_json(changed=True)

def main(**params):
    module = AnsibleModule(params=params,
        argument_spec = dict(
            state = dict(default='installed', choices=['installed', 'latest', 'removed', 'absent', 'present']),
            update_cache = dict(aliases=['update-cache'], type='bool'),
            purge = dict(default='no', type='bool'),
            package = dict(default=None, aliases=['pkg', 'name']),
            default_release = dict(default=None, aliases=['default-release']),
            install_recommends = dict(default='yes', aliases=['install-recommends'], type='bool'),
            force = dict(default='no', type='bool'),
            upgrade = dict(choices=['yes', 'dist'])
        ),
        mutually_exclusive = [['package', 'upgrade']],
        required_one_of = [['package', 'upgrade', 'update_cache']],
        supports_check_mode = True
    )

    try:
        import apt
        import apt_pkg
    except:
        module.fail_json(msg="Could not import python modules: apt, apt_pkg. Please install python-apt package.")

    if not os.path.exists(APT_PATH):
        module.fail_json(msg="Cannot find apt-get")

    p = module.params
    install_recommends = p['install_recommends']

    try:
        cache = apt.Cache()
        if p['default_release']:
            apt_pkg.config['APT::Default-Release'] = p['default_release']
            # reopen cache w/ modified config
            cache.open(progress=None)

        if p['update_cache']:
            cache.update()
            cache.open(progress=None)
            if not p['package']:
                return module.exit_json(changed=False)

        force_yes = p['force']

        if p['upgrade']:
            upgrade(module, p['upgrade'])

        packages = p['package'].split(',')
        latest = p['state'] == 'latest'
        for package in packages:
            if package.count('=') > 1:
                module.fail_json(msg="invalid package spec: %s" % package)
            if latest and '=' in package:
                module.fail_json(msg='version number inconsistent with state=latest: %s' % package)

        if p['state'] == 'latest':
            install(module, packages, cache, upgrade=True,
                    default_release=p['default_release'],
                    install_recommends=install_recommends,
                    force=force_yes)
        elif p['state'] in [ 'installed', 'present' ]:
            install(module, packages, cache, default_release=p['default_release'],
                      install_recommends=install_recommends,force=force_yes)
        elif p['state'] in [ 'removed', 'absent' ]:
            remove(module, packages, cache, p['purge'])

    except apt.cache.LockFailedException:
        module.fail_json(msg="Failed to lock apt for exclusive operation")

# this is magic, see lib/ansible/module_common.py

from newcommon import *


