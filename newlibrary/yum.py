#!/usr/bin/python -tt
# -*- coding: utf-8 -*-

# (c) 2012, Red Hat, Inc
# Written by Seth Vidal <skvidal at fedoraproject.org>
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
#


import traceback
import os
import yum

DOCUMENTATION = '''
---
module: yum
short_description: Manages packages with the I(yum) package manager
description:
     - Will install, upgrade, remove, and list packages with the I(yum) package manager.
options:
  name:
    description:
      - package name, or package specifier with version, like C(name-1.0).
    required: true
    default: null
    aliases: []
  list:
    description:
      - various non-idempotent commands for usage with C(/usr/bin/ansible) and I(not) playbooks. See examples.
    required: false
    default: null
  state:
    description:
      - whether to install (C(present), C(latest)), or remove (C(absent)) a package.
    required: false
    choices: [ "present", "latest", "absent" ]
    default: "present"
  enablerepo:
    description:
      - Repoid of repositories to enable for the install/update operation.
        These repos will not persist beyond the transaction
        multiple repos separated with a ','
    required: false
    version_added: "0.9"
    default: null
    aliases: []
    
  disablerepo:
    description:
      - I(repoid) of repositories to disable for the install/update operation
        These repos will not persist beyond the transaction
        Multiple repos separated with a ','
    required: false
    version_added: "0.9"
    default: null
    aliases: []
    
examples:
   - code: yum name=httpd state=latest
   - code: yum name=httpd state=removed
   - code: yum name=httpd enablerepo=testing state=installed
notes: []
# informational: requirements for nodes
requirements: [ yum, rpm ]
author: Seth Vidal
'''

def_qf = "%{name}-%{version}-%{release}.%{arch}"

repoquery='/usr/bin/repoquery'
if not os.path.exists(repoquery):
    repoquery = None

yumbin='/usr/bin/yum'

def yum_base(conf_file=None, cachedir=False):

    my = yum.YumBase()
    my.preconf.debuglevel=0
    my.preconf.errorlevel=0
    if conf_file and os.path.exists(conf_file):
        my.preconf.fn = conf_file
    if cachedir or os.geteuid() != 0:
        if hasattr(my, 'setCacheDir'):
            my.setCacheDir()
        else:
            cachedir = yum.misc.getCacheDir()
            my.repos.setCacheDir(cachedir)
            my.conf.cache = 0 

    return my

def po_to_nevra(po):

    if hasattr(po, 'ui_nevra'):
        return po.ui_nevra
    else:
        return '%s-%s-%s.%s' % (po.name, po.version, po.release, po.arch)

def is_installed(module, repoq, pkgspec, conf_file, qf=def_qf, en_repos=[], dis_repos=[]):

    if not repoq:

        pkgs = []
        try:
            my = yum_base(conf_file)
            for rid in en_repos:
                my.repos.enableRepo(rid)
            for rid in dis_repos:
                my.repos.disableRepo(rid)
                
            e,m,u = my.rpmdb.matchPackageNames([pkgspec])
            pkgs = e + m
            if not pkgs:
                pkgs.extend(my.returnInstalledPackagesByDep(pkgspec))
        except Exception, e:
            module.fail_json(msg="Failure talking to yum: %s" % e)

        return [ po_to_nevra(p) for p in pkgs ]

    else:

        cmd = repoq + ["--disablerepo=*", "--pkgnarrow=installed", "--qf", qf, pkgspec]
        rc,out,err = module.run_command(cmd)
        cmd = repoq + ["--disablerepo=*", "--pkgnarrow=installed", "--qf", qf, "--whatprovides", pkgspec]
        rc2,out2,err2 = module.run_command(cmd)
        if rc == 0 and rc2 == 0:
            out += out2
            return [ p for p in out.split('\n') if p.strip() ]
        else:
            module.fail_json(msg='Error from repoquery: %s: %s' % (cmd, err + err2))
            
    return []

def is_available(module, repoq, pkgspec, conf_file, qf=def_qf, en_repos=[], dis_repos=[]):

    if not repoq:

        pkgs = []
        try:
            my = yum_base(conf_file)
            for rid in en_repos:
                my.repos.enableRepo(rid)
            for rid in dis_repos:
                my.repos.disableRepo(rid)

            e,m,u = my.pkgSack.matchPackageNames([pkgspec])
            pkgs = e + m
            if not pkgs:
                pkgs.extend(my.returnPackagesByDep(pkgspec))
        except Exception, e:
            module.fail_json(msg="Failure talking to yum: %s" % e)
            
        return [ po_to_nevra(p) for p in pkgs ]

    else:
        myrepoq = list(repoq)

        for repoid in en_repos:
            r_cmd = ['--enablerepo', repoid]
            myrepoq.extend(r_cmd)
    
        for repoid in dis_repos:
            r_cmd = ['--disablerepo', repoid]
            myrepoq.extend(r_cmd)

        cmd = myrepoq + ["--qf", qf, pkgspec]
        rc,out,err = module.run_command(cmd)
        if rc == 0:
            return [ p for p in out.split('\n') if p.strip() ]
        else:
            module.fail_json(msg='Error from repoquery: %s: %s' % (cmd, err))

            
    return []

def is_update(module, repoq, pkgspec, conf_file, qf=def_qf, en_repos=[], dis_repos=[]):

    if not repoq:

        retpkgs = []
        pkgs = []
        updates = []

        try:
            my = yum_base(conf_file)
            for rid in en_repos:
                my.repos.enableRepo(rid)
            for rid in dis_repos:
                my.repos.disableRepo(rid)

            pkgs = my.returnPackagesByDep(pkgspec) + my.returnInstalledPackagesByDep(pkgspec)
            if not pkgs:
                e,m,u = my.pkgSack.matchPackageNames([pkgspec])
                pkgs = e + m
            updates = my.doPackageLists(pkgnarrow='updates').updates 
        except Exception, e:
            module.fail_json(msg="Failure talking to yum: %s" % e)

        for pkg in pkgs:
            if pkg in updates:
                retpkgs.append(pkg)
            
        return set([ po_to_nevra(p) for p in retpkgs ])

    else:
        myrepoq = list(repoq)
        for repoid in en_repos:
            r_cmd = ['--enablerepo', repoid]
            myrepoq.extend(r_cmd)
    
        for repoid in dis_repos:
            r_cmd = ['--disablerepo', repoid]
            myrepoq.extend(r_cmd)


        cmd = myrepoq + ["--pkgnarrow=updates", "--qf", qf, pkgspec]
        rc,out,err = module.run_command(cmd)
        
        if rc == 0:
            return set([ p for p in out.split('\n') if p.strip() ])
        else:
            module.fail_json(msg='Error from repoquery: %s: %s' % (cmd, err))
            
    return []

def what_provides(module, repoq, req_spec, conf_file,  qf=def_qf, en_repos=[], dis_repos=[]):

    if not repoq:

        pkgs = []
        try:
            my = yum_base(conf_file)
            for rid in en_repos:
                my.repos.enableRepo(rid)
            for rid in dis_repos:
                my.repos.disableRepo(rid)

            pkgs = my.returnPackagesByDep(req_spec) + my.returnInstalledPackagesByDep(req_spec)
            if not pkgs:
                e,m,u = my.pkgSack.matchPackageNames([req_spec])
                pkgs.extend(e)
                pkgs.extend(m)
                e,m,u = my.rpmdb.matchPackageNames([req_spec])
                pkgs.extend(e)
                pkgs.extend(m)
        except Exception, e:
            module.fail_json(msg="Failure talking to yum: %s" % e)

        return set([ po_to_nevra(p) for p in pkgs ])

    else:
        myrepoq = list(repoq)
        for repoid in en_repos:
            r_cmd = ['--enablerepo', repoid]
            myrepoq.extend(r_cmd)
    
        for repoid in dis_repos:
            r_cmd = ['--disablerepo', repoid]
            myrepoq.extend(r_cmd)

        cmd = myrepoq + ["--qf", qf, "--whatprovides", req_spec]
        rc,out,err = module.run_command(cmd)
        cmd = myrepoq + ["--qf", qf, req_spec]
        rc2,out2,err2 = module.run_command(cmd)
        if rc == 0 and rc2 == 0:
            out += out2
            pkgs = set([ p for p in out.split('\n') if p.strip() ])
            if not pkgs:
                pkgs = is_installed(module, repoq, req_spec, conf_file, qf=qf)
            return pkgs
        else:
            module.fail_json(msg='Error from repoquery: %s: %s' % (cmd, err + err2))

    return []

def local_nvra(module, path):
    """return nvra of a local rpm passed in"""
    
    cmd = ['/bin/rpm', '-qp' ,'--qf', 
            '%{name}-%{version}-%{release}.%{arch}\n', path ]
    rc, out, err = module.run_command(cmd)
    if rc != 0:
        return None
    nvra = out.split('\n')[0]
    return nvra
    
def pkg_to_dict(pkgstr):

    if pkgstr.strip():
        n,e,v,r,a,repo = pkgstr.split('|')
    else:
        return {'error_parsing': pkgstr}

    d = {
        'name':n,
        'arch':a,
        'epoch':e,
        'release':r,
        'version':v,
        'repo':repo,
        'nevra': '%s:%s-%s-%s.%s' % (e,n,v,r,a)
    }

    if repo == 'installed':
        d['yumstate'] = 'installed'
    else:
        d['yumstate'] = 'available'

    return d

def repolist(module, repoq, qf="%{repoid}"):

    cmd = repoq + ["--qf", qf, "-a"]
    rc,out,err = module.run_command(cmd)
    ret = []
    if rc == 0:
        ret = set([ p for p in out.split('\n') if p.strip() ])
    return ret

def list_stuff(module, conf_file, stuff):

    qf = "%{name}|%{epoch}|%{version}|%{release}|%{arch}|%{repoid}"
    repoq = [repoquery, '--show-duplicates', '--plugins', '--quiet', '-q']
    if conf_file and os.path.exists(conf_file):
        repoq += ['-c', conf_file]

    if stuff == 'installed':
        return [ pkg_to_dict(p) for p in is_installed(module, repoq, '-a', conf_file, qf=qf) if p.strip() ]
    elif stuff == 'updates':
        return [ pkg_to_dict(p) for p in is_update(module, repoq, '-a', conf_file, qf=qf) if p.strip() ]
    elif stuff == 'available':
        return [ pkg_to_dict(p) for p in is_available(module, repoq, '-a', conf_file, qf=qf) if p.strip() ]
    elif stuff == 'repos':
        return [ dict(repoid=name, state='enabled') for name in repolist(module, repoq) if name.strip() ]
    else:
        return [ pkg_to_dict(p) for p in is_installed(module, repoq, stuff, conf_file, qf=qf) + is_available(module, repoq, stuff, conf_file, qf=qf) if p.strip() ]

def install(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos):

    res = {}
    res['results'] = []
    res['msg'] = ''
    res['rc'] = 0
    res['changed'] = False

    for spec in items:
        pkg = None

        # check if pkgspec is installed (if possible for idempotence)
        # localpkg
        if spec.endswith('.rpm'):
            # get the pkg name-v-r.arch
            if not os.path.exists(spec):
                res['msg'] += "No Package file matching '%s' found on system" % spec
                module.fail_json(**res)

            nvra = local_nvra(module, spec)
            # look for them in the rpmdb
            if is_installed(module, repoq, nvra, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                # if they are there, skip it
                continue
            pkg = spec
        #groups :(
        elif  spec.startswith('@'):
            # complete wild ass guess b/c it's a group
            pkg = spec

        # range requires or file-requires or pkgname :(
        else:
            # look up what pkgs provide this
            pkglist = what_provides(module, repoq, spec, conf_file, en_repos=en_repos, dis_repos=dis_repos)
            if not pkglist:
                res['msg'] += "No Package matching '%s' found available, installed or updated" % spec
                module.fail_json(**res)

            # if any of them are installed
            # then nothing to do

            found = False
            for this in pkglist:
                if is_installed(module, repoq, this, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                    found = True
                    res['results'].append('%s providing %s is already installed' % (this, spec))
                    break

            # if the version of the pkg you have installed is not in ANY repo, but there are
            # other versions in the repos (both higher and lower) then the previous checks won't work.
            # so we check one more time. This really only works for pkgname - not for file provides or virt provides
            # but virt provides should be all caught in what_provides on its own.
            # highly irritating
            if not found:
                if is_installed(module, repoq, spec, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                    found = True
                    res['results'].append('package providing %s is already installed' % (spec))
                    
            if found:
                continue
            # if not - then pass in the spec as what to install
            # we could get here if nothing provides it but that's not
            # the error we're catching here
            pkg = spec

        cmd = yum_basecmd + ['install', pkg]

        if module.check_mode:
            return module.exit_json(changed=True)

        rc, out, err = module.run_command(cmd)

        res['rc'] += rc
        res['results'].append(out)
        res['msg'] += err

        # FIXME - if we did an install - go and check the rpmdb to see if it actually installed
        # look for the pkg in rpmdb
        # look for the pkg via obsoletes
        if not rc:
            res['changed'] = True

    return module.exit_json(**res)


def remove(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos):

    res = {}
    res['results'] = []
    res['msg'] = ''
    res['changed'] = False
    res['rc'] = 0

    for pkg in items:
        is_group = False
        # group remove - this is doom on a stick
        if pkg.startswith('@'):
            is_group = True
        else:
            if not is_installed(module, repoq, pkg, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                res['results'].append('%s is not installed' % pkg)
                continue

        # run an actual yum transaction
        cmd = yum_basecmd + ["remove", pkg]

        if module.check_mode:
            return module.exit_json(changed=True)

        rc, out, err = module.run_command(cmd)

        res['rc'] += rc
        res['results'].append(out)
        res['msg'] += err

        # compile the results into one batch. If anything is changed 
        # then mark changed
        # at the end - if we've end up failed then fail out of the rest
        # of the process

        # at this point we should check to see if the pkg is no longer present
        
        if not is_group: # we can't sensibly check for a group being uninstalled reliably
            # look to see if the pkg shows up from is_installed. If it doesn't
            if not is_installed(module, repoq, pkg, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                res['changed'] = True
            else:
                module.fail_json(**res)

        if rc != 0:
            module.fail_json(**res)
            
    return module.exit_json(**res)

def latest(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos):

    res = {}
    res['results'] = []
    res['msg'] = ''
    res['changed'] = False
    res['rc'] = 0

    for spec in items:

        pkg = None
        basecmd = 'update'
        # groups, again
        if spec.startswith('@'):
            pkg = spec
        # dep/pkgname  - find it
        else:
            if is_installed(module, repoq, spec, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                basecmd = 'update'
            else:
                basecmd = 'install'

            pkglist = what_provides(module, repoq, spec, conf_file, en_repos=en_repos, dis_repos=dis_repos)
            if not pkglist:
                res['msg'] += "No Package matching '%s' found available, installed or updated" % spec
                module.fail_json(**res)
            
            nothing_to_do = True
            for this in pkglist:
                if basecmd == 'install' and is_available(module, repoq, this, conf_file, en_repos=en_repos, dis_repos=dis_repos):
                    nothing_to_do = False
                    break
                    
                if basecmd == 'update' and is_update(module, repoq, this, conf_file, en_repos=en_repos, dis_repos=en_repos):
                    nothing_to_do = False
                    break
                    
            if nothing_to_do:
                res['results'].append("All packages providing %s are up to date" % spec)
                continue

            pkg = spec

        cmd = yum_basecmd + [basecmd, pkg]

        if module.check_mode:
            return module.exit_json(changed=True)

        rc, out, err = module.run_command(cmd)

        res['rc'] += rc
        res['results'].append(out)
        res['msg'] += err

        # FIXME if it is - update it and check to see if it applied
        # check to see if there is no longer an update available for the pkgspec

        if rc:
            res['failed'] = True
        else:
            res['changed'] = True

    return module.exit_json(**res)

def ensure(module, state, pkgspec, conf_file, enablerepo, disablerepo):

    # take multiple args comma separated
    items = pkgspec.split(',')

    yum_basecmd = [yumbin, '-d', '1', '-y']

        
    if not repoquery:
        repoq = None
    else:
        repoq = [repoquery, '--show-duplicates', '--plugins', '--quiet', '-q']

    if conf_file and os.path.exists(conf_file):
        yum_basecmd += ['-c', conf_file]
        if repoq:
            repoq += ['-c', conf_file]

    dis_repos =[]
    en_repos = []
    if disablerepo:
        dis_repos = disablerepo.split(',')
    if enablerepo:
        en_repos = enablerepo.split(',')

    for repoid in en_repos:
        r_cmd = ['--enablerepo', repoid]
        yum_basecmd.extend(r_cmd)
        
    for repoid in dis_repos:
        r_cmd = ['--disablerepo', repoid]
        yum_basecmd.extend(r_cmd)

    if state in ['installed', 'present', 'latest']:
        my = yum_base(conf_file)
        try:
            for r in dis_repos:
                my.repos.disableRepo(r)

            for r in en_repos:
                try:
                    my.repos.enableRepo(r)
                    rid = my.repos.getRepo(r)
                    a = rid.repoXML.repoid
                except yum.Errors.YumBaseError, e:
                    module.fail_json(msg="Error setting/accessing repo %s: %s" % (r, e))
        except yum.Errors.YumBaseError, e:
            module.fail_json(msg="Error accessing repos: %s" % e)

    if state in ['installed', 'present']:
        install(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos)
    elif state in ['removed', 'absent']:
        remove(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos)
    elif state == 'latest':
        latest(module, items, repoq, yum_basecmd, conf_file, en_repos, dis_repos)

    # should be caught by AnsibleModule argument_spec
    return dict(changed=False, failed=True, results='', errors='unexpected state')

def main(**params):

    # state=installed name=pkgspec
    # state=removed name=pkgspec
    # state=latest name=pkgspec
    #
    # informational commands:
    #   list=installed
    #   list=updates
    #   list=available
    #   list=repos
    #   list=pkgspec

    module = AnsibleModule(params=params,
        argument_spec = dict(
            name=dict(aliases=['pkg']),
            # removed==absent, installed==present, these are accepted as aliases
            state=dict(default='installed', choices=['absent','present','installed','removed','latest']),
            enablerepo=dict(),
            disablerepo=dict(),
            list=dict(),
            conf_file=dict(default=None),
        ),
        required_one_of = [['name','list']],
        mutually_exclusive = [['name','list']],
        supports_check_mode = True
    )

    params = module.params

    if params['list']:
        if not repoquery:
            module.fail_json(msg="repoquery is required to use list= with this module. Please install the yum-utils package.")
        results = dict(results=list_stuff(module, params['conf_file'], params['list']))
        return module.exit_json(**results)

    else:
        pkg = params['name']
        state = params['state']
        enablerepo = params.get('enablerepo', '')
        disablerepo = params.get('disablerepo', '')
        res = ensure(module, state, pkg, params['conf_file'], enablerepo, disablerepo)
        module.fail_json(msg="we should never get here unless this all failed", **res)

# this is magic, see lib/ansible/module_common.py

from newcommon import *


