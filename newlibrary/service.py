#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
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
module: service
author: Michael DeHaan
version_added: 0.1
short_description:  Manage services.
description:
    - Controls services on remote hosts.
options:
    name:
        required: true
        description:
        - Name of the service.
    state:
        required: false
        choices: [ started, stopped, restarted, reloaded ]
        description:
          - C(started)/C(stopped) are idempotent actions that will not run
            commands unless necessary.  C(restarted) will always bounce the
            service.  C(reloaded) will always reload.
    pattern:
        required: false
        version_added: "0.7"
        description:
        - If the service does not respond to the status command, name a
          substring to look for as would be found in the output of the I(ps)
          command as a stand-in for a status result.  If the string is found,
          the service will be assumed to be running.
    enabled:
        required: false
        choices: [ "yes", "no" ]
        description:
        - Whether the service should start on boot.
    arguments:
        description:
        - Additional arguments provided on the command line
        aliases: [ 'args' ]
examples:
    - description: Example action to start service httpd, if not running
      code: "service: name=httpd state=started"
    - description: Example action to stop service httpd, if running
      code: "service: name=httpd state=stopped"
    - description: Example action to restart service httpd, in all cases
      code: "service: name=httpd state=restarted"
    - description: Example action to reload service httpd, in all cases
      code: "service: name=httpd state=reloaded"
    - description: Example action to start service foo, based on running process /usr/bin/foo
      code: "service: name=foo pattern=/usr/bin/foo state=started"
    - description: Example action to restart network service for interface eth0
      code: "service: name=network state=restarted args=eth0"
'''

import platform
import os
import tempfile
import shlex
import select

class Service(object):
    """
    This is the generic Service manipulation class that is subclassed
    based on platform.

    A subclass should override the following action methods:-
      - get_service_tools
      - service_enable
      - get_service_status
      - service_control

    All subclasses MUST define platform and distribution (which may be None).
    """

    platform = 'Generic'
    distribution = None

    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(Service, args, kwargs)

    def __init__(self, module):
        self.module         = module
        self.name           = module.params['name']
        self.state          = module.params['state']
        self.pattern        = module.params['pattern']
        self.enable         = module.params['enabled']
        self.changed        = False
        self.running        = None
        self.action         = None
        self.svc_cmd        = None
        self.svc_initscript = None
        self.svc_initctl    = None
        self.enable_cmd     = None
        self.arguments      = module.params.get('arguments', '')
        self.rcconf_file    = None
        self.rcconf_key     = None
        self.rcconf_value   = None

        # select whether we dump additional debug info through syslog
        self.syslogging = False

    # ===========================================
    # Platform specific methods (must be replaced by subclass).

    def get_service_tools(self):
        self.module.fail_json(msg="get_service_tools not implemented on target platform")

    def service_enable(self):
        self.module.fail_json(msg="service_enable not implemented on target platform")

    def get_service_status(self):
        self.module.fail_json(msg="get_service_status not implemented on target platform")

    def service_control(self):
        self.module.fail_json(msg="service_control not implemented on target platform")

    # ===========================================
    # Generic methods that should be used on all platforms.

    def execute_command(self, cmd, daemonize=False):
        if self.syslogging:
            syslog.openlog('ansible-%s' % os.path.basename(__file__))
            syslog.syslog(syslog.LOG_NOTICE, 'Command %s, daemonize %r' % (cmd, daemonize))

        # Most things don't need to be daemonized
        if not daemonize:
            return self.module.run_command(cmd)

        # This is complex because daemonization is hard for people.
        # What we do is daemonize a part of this module, the daemon runs the
        # command, picks up the return code and output, and returns it to the
        # main process.
        pipe = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(pipe[0])
            # Set stdin/stdout/stderr to /dev/null
            fd = os.open(os.devnull, os.O_RDWR)
            if fd != 0:
                os.dup2(fd, 0)
            if fd != 1:
                os.dup2(fd, 1)
            if fd != 2:
                os.dup2(fd, 2)
            if fd not in (0, 1, 2):
                os.close(fd)

            # Make us a daemon. Yes, that's all it takes.
            pid = os.fork()
            if pid > 0:
                os._exit(0)
            os.setsid()
            os.chdir("/")
            pid = os.fork()
            if pid > 0:
                os._exit(0)

            # Start the command
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=lambda: os.close(pipe[1]))
            stdout = ""
            stderr = ""
            fds = [p.stdout, p.stderr]
            # Wait for all output, or until the main process is dead and its output is done.
            while fds:
                rfd, wfd, efd = select.select(fds, [], fds, 1)
                if not (rfd + wfd + efd) and p.poll() is not None:
                    break
                if p.stdout in rfd:
                    dat = os.read(p.stdout.fileno(), 4096)
                    if not dat:
                        fds.remove(p.stdout)
                    stdout += dat
                if p.stderr in rfd:
                    dat = os.read(p.stderr.fileno(), 4096)
                    if not dat:
                        fds.remove(p.stderr)
                    stderr += dat
            p.wait()
            # Return a JSON blob to parent
            os.write(pipe[1], json.dumps([p.returncode, stdout, stderr]))
            os.close(pipe[1])
            os._exit(0)
        elif pid == -1:
            self.module.fail_json(msg="unable to fork")
        else:
            os.close(pipe[1])
            os.waitpid(pid, 0)
            # Wait for data from daemon process and process it.
            data = ""
            while True:
                rfd, wfd, efd = select.select([pipe[0]], [], [pipe[0]])
                if pipe[0] in rfd:
                    dat = os.read(pipe[0], 4096)
                    if not dat:
                        break
                    data += dat
            return json.loads(data)

    def check_ps(self):
        # Set ps flags
        if platform.system() == 'SunOS':
            psflags = '-ef'
        else:
            psflags = 'auxww'

        # Find ps binary
        psbin = self.module.get_bin_path('ps', True)

        (rc, psout, pserr) = self.execute_command('%s %s' % (psbin, psflags))
        # If rc is 0, set running as appropriate
        if rc == 0:
            self.running = False
            lines = psout.split("\n")
            for line in lines:
                if self.pattern in line and not "pattern=" in line:
                    # so as to not confuse ./hacking/test-module
                    self.running = True
                    break

    def check_service_changed(self):
        if self.state and self.running is None:
            self.module.fail_json(msg="failed determining service state, possible typo of service name?")
        # Find out if state has changed
        if not self.running and self.state in ["started", "running"]:
            self.changed = True
        elif self.running and self.state in ["stopped","reloaded"]:
            self.changed = True
        elif self.state == "restarted":
            self.changed = True
        if self.module.check_mode and self.changed:
            self.return module.exit_json(changed=True, msg='service state changed')

    def modify_service_state(self):

        # Only do something if state will change
        if self.changed:
            # Control service
            if self.state in ['started', 'running']:
                self.action = "start"
            elif self.state == 'stopped':
                self.action = "stop"
            elif self.state == 'reloaded':
                self.action = "reload"
            elif self.state == 'restarted':
                self.action = "restart"

            if self.module.check_mode:
                self.return module.exit_json(changed=True, msg='changing service state')

            return self.service_control()

        else:
            # If nothing needs to change just say all is well
            rc = 0
            err = ''
            out = ''
            return rc, out, err

    def service_enable_rcconf(self):
        if self.rcconf_file is None or self.rcconf_key is None or self.rcconf_value is None:
            self.module.fail_json(msg="service_enable_rcconf() requires rcconf_file, rcconf_key and rcconf_value")

        changed = None
        entry = '%s="%s"\n' % (self.rcconf_key, self.rcconf_value)
        RCFILE = open(self.rcconf_file, "r")
        new_rc_conf = []

        # Build a list containing the possibly modified file.
        for rcline in RCFILE:
            # Parse line removing whitespaces, quotes, etc.
            rcarray = shlex.split(rcline, comments=True)
            if len(rcarray) >= 1 and '=' in rcarray[0]:
                (key, value) = rcarray[0].split("=", 1)
                if key == self.rcconf_key:
                    if value == self.rcconf_value:
                        # Since the proper entry already exists we can stop iterating.
                        changed = False
                        break
                    else:
                        # We found the key but the value is wrong, replace with new entry.
                        rcline = entry
                        changed = True

            # Add line to the list.
            new_rc_conf.append(rcline)

        # We are done with reading the current rc.conf, close it.
        RCFILE.close()

        # If we did not see any trace of our entry we need to add it.
        if changed is None:
            new_rc_conf.append(entry)
            changed = True

        if changed is True:

            if self.module.check_mode:
                self.return module.exit_json(changed=True, msg="changing service enablement")

            # Create a temporary file next to the current rc.conf (so we stay on the same filesystem).
            # This way the replacement operation is atomic.
            rcconf_dir = os.path.dirname(self.rcconf_file)
            rcconf_base = os.path.basename(self.rcconf_file)
            (TMP_RCCONF, tmp_rcconf_file) = tempfile.mkstemp(dir=rcconf_dir, prefix="%s-" % rcconf_base)

            # Write out the contents of the list into our temporary file.
            for rcline in new_rc_conf:
                os.write(TMP_RCCONF, rcline)

            # Close temporary file.
            os.close(TMP_RCCONF)

            # Replace previous rc.conf.
            self.module.atomic_replace(tmp_rcconf_file, self.rcconf_file)

# ===========================================
# Subclass: Linux

class LinuxService(Service):
    """
    This is the Linux Service manipulation class - it is currently supporting
    a mixture of binaries and init scripts for controlling services started at
    boot, as well as for controlling the current state.
    """

    platform = 'Linux'
    distribution = None

    def get_service_tools(self):

        paths = [ '/sbin', '/usr/sbin', '/bin', '/usr/bin' ]
        binaries = [ 'service', 'chkconfig', 'update-rc.d', 'initctl', 'systemctl', 'start', 'stop', 'restart' ]
        initpaths = [ '/etc/init.d' ]
        location = dict()

        for binary in binaries:
            location[binary] = None
        for binary in binaries:
            location[binary] = self.module.get_bin_path(binary)

        # Locate a tool for enable options
        if location.get('chkconfig', None) and os.path.exists("/etc/init.d/%s" % self.name):
            # we are using a standard SysV service
            self.enable_cmd = location['chkconfig']
        elif location.get('update-rc.d', None) and os.path.exists("/etc/init/%s.conf" % self.name):
            # service is managed by upstart
            self.enable_cmd = location['update-rc.d']
        elif location.get('update-rc.d', None) and os.path.exists("/etc/init.d/%s" % self.name):
            # service is managed by with SysV init scripts, but with update-rc.d
            self.enable_cmd = location['update-rc.d']
        elif location.get('systemctl', None):

            # verify service is managed by systemd
            rc, out, err = self.execute_command("%s list-unit-files" % (location['systemctl']))

            # adjust the service name to account for template service unit files
            index = self.name.find('@')
            if index == -1:
                name = self.name
            else:
                name = self.name[:index+1]

            look_for = "%s.service" % name
            for line in out.splitlines():
               if line.startswith(look_for):
                   self.enable_cmd = location['systemctl']
                   break

        # Locate a tool for runtime service management (start, stop etc.)
        self.svc_cmd = ''
        if location.get('service', None) and os.path.exists("/etc/init.d/%s" % self.name):
            # SysV init script
            self.svc_cmd = location['service']
        elif location.get('start', None) and os.path.exists("/etc/init/%s.conf" % self.name):
            # upstart -- rather than being managed by one command, start/stop/restart are actual commands
            self.svc_cmd = ''
        else:
            # still a SysV init script, but /sbin/service isn't installed
            for initdir in initpaths:
                initscript = "%s/%s" % (initdir,self.name)
                if os.path.isfile(initscript):
                    self.svc_initscript = initscript

        # couldn't find anything yet, assume systemd
        if self.svc_initscript is None:
            if location.get('systemctl'):
                self.svc_cmd = location['systemctl']

        if self.svc_cmd is None and not self.svc_initscript:
            self.module.fail_json(msg='cannot find \'service\' binary or init script for service, aborting')

        if location.get('initctl', None):
            self.svc_initctl = location['initctl']

    def get_service_status(self):
        self.action = "status"
        rc, status_stdout, status_stderr = self.service_control()

        # if we have decided the service is managed by upstart, we check for some additional output...
        if self.svc_initctl and self.running is None:
            # check the job status by upstart response
            initctl_rc, initctl_status_stdout, initctl_status_stderr = self.execute_command("%s status %s" % (self.svc_initctl, self.name))
            if initctl_status_stdout.find("stop/waiting") != -1:
                self.running = False
            elif initctl_status_stdout.find("start/running") != -1:
                self.running = True

        # if the job status is still not known check it by response code
        # For reference, see:
        # http://refspecs.linuxbase.org/LSB_4.1.0/LSB-Core-generic/LSB-Core-generic/iniscrptact.html
        if self.running is None:
            if rc in [1, 2, 3, 4, 69]:
                self.running = False
            elif rc == 0:
                self.running = True

        # if the job status is still not known check it by status output keywords
        if self.running is None:
            # first tranform the status output that could irritate keyword matching
            cleanout = status_stdout.lower().replace(self.name.lower(), '')
            if "stop" in cleanout:
                self.running = False
            elif "run" in cleanout and "not" in cleanout:
                self.running = False
            elif "run" in cleanout and "not" not in cleanout:
                self.running = True
            elif "start" in cleanout and "not" not in cleanout:
                self.running = True
            elif 'could not access pid file' in cleanout:
                self.running = False
            elif 'is dead and pid file exists' in cleanout:
                self.running = False
            elif 'dead but subsys locked' in cleanout:
                self.running = False
            elif 'dead but pid file exists' in cleanout:
                self.running = False

        # if the job status is still not known check it by special conditions
        if self.running is None:
            if self.name == 'iptables' and status_stdout.find("ACCEPT") != -1:
                # iptables status command output is lame
                # TODO: lookup if we can use a return code for this instead?
                self.running = True

        return self.running


    def service_enable(self):

        if self.enable_cmd is None:
            self.module.fail_json(msg='service name not recognized')

        # FIXME: we use chkconfig or systemctl
        # to decide whether to run the command here but need something
        # similar for upstart

        if self.enable_cmd.endswith("chkconfig"):
            (rc, out, err) = self.execute_command("%s --list %s" % (self.enable_cmd, self.name))
            if 'chkconfig --add %s' % self.name in err:
                self.execute_command("%s --add %s" % (self.enable_cmd, self.name))
                (rc, out, err) = self.execute_command("%s --list %s" % (self.enable_cmd, self.name))
            if not self.name in out:
                self.module.fail_json(msg="unknown service name")
            state = out.split()[-1]
            if self.enable and ( "3:on" in out and "5:on" in out ):
                return
            elif not self.enable and ( "3:off" in out and "5:off" in out ):
                return

        if self.enable_cmd.endswith("systemctl"):
            (rc, out, err) = self.execute_command("%s show %s.service" % (self.enable_cmd, self.name))

            d = dict(line.split('=', 1) for line in out.splitlines())
            if "UnitFileState" in d:
                if self.enable and d["UnitFileState"] == "enabled":
                    return
                elif not self.enable and d["UnitFileState"] == "disabled":
                    return
            elif not self.enable:
                return

        # we change argument depending on real binary used
        # update-rc.d wants enable/disable while
        # chkconfig wants on/off
        # also, systemctl needs the argument order reversed
        if self.enable:
            on_off = "on"
            enable_disable = "enable"
        else:
            on_off = "off"
            enable_disable = "disable"

        if self.enable_cmd.endswith("update-rc.d"):
            args = (self.enable_cmd, self.name, enable_disable)
        elif self.enable_cmd.endswith("systemctl"):
            args = (self.enable_cmd, enable_disable, self.name + ".service")
        else:
            args = (self.enable_cmd, self.name, on_off)

        self.changed = True

        if self.module.check_mode and self.changed:
            self.return module.exit_json(changed=True)

        return self.execute_command("%s %s %s" % args)


    def service_control(self):

        # Decide what command to run
        svc_cmd = ''
        arguments = self.arguments
        if self.svc_cmd:
            if not self.svc_cmd.endswith("systemctl"):
                # SysV take the form <cmd> <name> <action>
                svc_cmd = "%s %s" % (self.svc_cmd, self.name)
            else:
                # systemd commands take the form <cmd> <action> <name>
                svc_cmd = self.svc_cmd
                arguments = "%s %s" % (self.name, arguments)
        elif self.svc_initscript:
            # upstart
            svc_cmd = "%s" % self.svc_initscript

        if self.action is not "restart":
            if svc_cmd != '':
                # upstart or systemd
                rc_state, stdout, stderr = self.execute_command("%s %s %s" % (svc_cmd, self.action, arguments), daemonize=True)
            else:
                # SysV
                rc_state, stdout, stderr = self.execute_command("%s %s %s" % (self.action, self.name, arguments), daemonize=True)
        else:
            # not all services support restart. Do it the hard way.
            if svc_cmd != '':
                # upstart or systemd
                rc1, stdout1, stderr1 = self.execute_command("%s %s %s" % (svc_cmd, 'stop', arguments), daemonize=True)
            else:
                # SysV
                rc1, stdout1, stderr1 = self.execute_command("%s %s %s" % ('stop', self.name, arguments), daemonize=True)

            if svc_cmd != '':
                # upstart or systemd
                rc2, stdout2, stderr2 = self.execute_command("%s %s %s" % (svc_cmd, 'start', arguments), daemonize=True)
            else:
                # SysV
                rc2, stdout2, stderr2 = self.execute_command("%s %s %s" % ('start', self.name, arguments), daemonize=True)

            # merge return information
            if rc1 != 0 and rc2 == 0:
                rc_state = rc2
                stdout = stdout2
                stderr = stderr2
            else:
                rc_state = rc1 + rc2
                stdout = stdout1 + stdout2
                stderr = stderr1 + stderr2

        return(rc_state, stdout, stderr)

# ===========================================
# Subclass: FreeBSD

class FreeBsdService(Service):
    """
    This is the FreeBSD Service manipulation class - it uses the /etc/rc.conf
    file for controlling services started at boot and the 'service' binary to
    check status and perform direct service manipulation.
    """

    platform = 'FreeBSD'
    distribution = None

    def get_service_tools(self):
        self.svc_cmd = self.module.get_bin_path('service', True)

        if not self.svc_cmd:
            self.module.fail_json(msg='unable to find service binary')

    def get_service_status(self):
        rc, stdout, stderr = self.execute_command("%s %s %s" % (self.svc_cmd, self.name, 'onestatus'))
        if rc == 1:
            self.running = False
        elif rc == 0:
            self.running = True

    def service_enable(self):
        if self.enable:
            self.rcconf_value = "YES"
        else:
            self.rcconf_value = "NO"

        rcfiles = [ '/etc/rc.conf','/usr/local/etc/rc.conf' ]
        for rcfile in rcfiles:
            if os.path.isfile(rcfile):
                self.rcconf_file = rcfile

        self.rcconf_key = "%s_enable" % self.name

        return self.service_enable_rcconf()

    def service_control(self):

        if self.action is "start":
            self.action = "onestart"
        if self.action is "stop":
            self.action = "onestop"
        if self.action is "reload":
            self.action = "onereload"

        return self.execute_command("%s %s %s" % (self.svc_cmd, self.name, self.action))

# ===========================================
# Subclass: OpenBSD

class OpenBsdService(Service):
    """
    This is the OpenBSD Service manipulation class - it uses /etc/rc.d for
    service control. Enabling a service is currently not supported because the
    <service>_flags variable is not boolean, you should supply a rc.conf.local
    file in some other way.
    """

    platform = 'OpenBSD'
    distribution = None

    def get_service_tools(self):
        rcdir = '/etc/rc.d'

        rc_script = "%s/%s" % (rcdir, self.name)
        if os.path.isfile(rc_script):
            self.svc_cmd = rc_script

        if not self.svc_cmd:
            self.module.fail_json(msg='unable to find rc.d script')

    def get_service_status(self):
        rc, stdout, stderr = self.execute_command("%s %s" % (self.svc_cmd, 'check'))
        if rc == 1:
            self.running = False
        elif rc == 0:
            self.running = True

    def service_control(self):
        return self.execute_command("%s %s" % (self.svc_cmd, self.action))

# ===========================================
# Subclass: NetBSD

class NetBsdService(Service):
    """
    This is the NetBSD Service manipulation class - it uses the /etc/rc.conf
    file for controlling services started at boot, check status and perform
    direct service manipulation. Init scripts in /etc/rcd are used for
    controlling services (start/stop) as well as for controlling the current
    state.
    """

    platform = 'NetBSD'
    distribution = None

    def get_service_tools(self):
        initpaths = [ '/etc/rc.d' ]		# better: $rc_directories - how to get in here? Run: sh -c '. /etc/rc.conf ; echo $rc_directories'

        for initdir in initpaths:
            initscript = "%s/%s" % (initdir,self.name)
            if os.path.isfile(initscript):
                self.svc_initscript = initscript

        if not self.svc_initscript:
            self.module.fail_json(msg='unable to find rc.d script')

    def service_enable(self):
        if self.enable:
            self.rcconf_value = "YES"
        else:
            self.rcconf_value = "NO"

        rcfiles = [ '/etc/rc.conf' ]		# Overkill?
        for rcfile in rcfiles:
            if os.path.isfile(rcfile):
                self.rcconf_file = rcfile

        self.rcconf_key = "%s" % self.name

        return self.service_enable_rcconf()

    def get_service_status(self):
        self.svc_cmd = "%s" % self.svc_initscript
        rc, stdout, stderr = self.execute_command("%s %s" % (self.svc_cmd, 'onestatus'))
        if rc == 1:
            self.running = False
        elif rc == 0:
            self.running = True

    def service_control(self):
        if self.action is "start":
            self.action = "onestart"
        if self.action is "stop":
            self.action = "onestop"

        self.svc_cmd = "%s" % self.svc_initscript
        return self.execute_command("%s %s" % (self.svc_cmd, self.action), daemonize=True)

# ===========================================
# Subclass: SunOS
class SunOSService(Service):
    """
    This is the SunOS Service manipulation class - it uses the svcadm
    command for controlling services, and svcs command for checking status.
    It also tries to be smart about taking the service out of maintenance
    state if necessary.
    """
    platform = 'SunOS'
    distribution = None

    def get_service_tools(self):
        self.svcs_cmd = self.module.get_bin_path('svcs', True)

        if not self.svcs_cmd:
            self.module.fail_json(msg='unable to find svcs binary')

        self.svcadm_cmd = self.module.get_bin_path('svcadm', True)
    
        if not self.svcadm_cmd:
            self.module.fail_json(msg='unable to find svcadm binary')

    def get_service_status(self):
        status = self.get_sunos_svcs_status()
        # Only 'online' is considered properly running. Everything else is off
        # or has some sort of problem.
        if status == 'online':
            self.running = True
        else:
            self.running = False

    def get_sunos_svcs_status(self):
        rc, stdout, stderr = self.execute_command("%s %s" % (self.svcs_cmd, self.name))
        if rc == 1:
            if stderr:
                self.module.fail_json(msg=stderr)
            else:
                self.module.fail_json(msg=stdout)

        lines = stdout.rstrip("\n").split("\n")
        status = lines[-1].split(" ")[0]
        # status is one of: online, offline, degraded, disabled, maintenance, uninitialized
        # see man svcs(1)
        return status

    def service_enable(self):
        # Get current service enablement status
        rc, stdout, stderr = self.execute_command("%s -l %s" % (self.svcs_cmd, self.name))

        if rc != 0:
            if stderr:
                self.module.fail_json(msg=stderr)
            else:
                self.module.fail_json(msg=stdout)

        enabled = False
        temporary = False

        # look for enabled line, which could be one of:
        #    enabled   true (temporary)
        #    enabled   false (temporary)
        #    enabled   true
        #    enabled   false
        for line in stdout.split("\n"):
            if line.find("enabled") == 0:
                if line.find("true") != -1:
                    enabled = True
                if line.find("temporary") != -1:
                    temporary = True
                
        startup_enabled = (enabled and not temporary) or (not enabled and temporary)
        
        if self.enable and startup_enabled:
            return
        elif (not self.enable) and (not startup_enabled):
            return

        # Mark service as started or stopped (this will have the side effect of
        # actually stopping or starting the service)
        if self.enable:
            subcmd = "enable -rs"
        else:
            subcmd = "disable -s"

        rc, stdout, stderr = self.execute_command("%s %s %s" % (self.svcadm_cmd, subcmd, self.name))

        if rc != 0:
            if stderr:
                self.module.fail_json(msg=stderr)
            else:
                self.module.fail_json(msg=stdout)

        self.changed = True
        
            
    def service_control(self):
        status = self.get_sunos_svcs_status()

        # if starting or reloading, clear maintenace states
        if self.action in ['start', 'reload', 'restart'] and status in ['maintenance', 'degraded']:
            rc, stdout, stderr = self.execute_command("%s clear %s" % (self.svcadm_cmd, self.name))
            if rc != 0:
                return rc, stdout, stderr
            status = self.get_sunos_svcs_status()

        if status in ['maintenance', 'degraded']:
            self.module.fail_json(msg="Failed to bring service out of %s status." % status)

        if self.action == 'start':
            subcmd = "enable -rst"
        elif self.action == 'stop':
            subcmd = "disable -st"
        elif self.action == 'reload':
            subcmd = "refresh"
        elif self.action == 'restart' and status == 'online':
            subcmd = "restart"
        elif self.action == 'restart' and status != 'online':
            subcmd = "enable -rst"
            
        return self.execute_command("%s %s %s" % (self.svcadm_cmd, subcmd, self.name))


# ===========================================
# Main control flow

def main(**params):
    module = AnsibleModule(params=params,
        argument_spec = dict(
            name = dict(required=True),
            state = dict(choices=['running', 'started', 'stopped', 'restarted', 'reloaded']),
            pattern = dict(required=False, default=None),
            enabled = dict(choices=BOOLEANS, type='bool'),
            arguments = dict(aliases=['args'], default=''),
        ),
        supports_check_mode=True
    )

    service = Service(module)

    if service.syslogging:
        syslog.openlog('ansible-%s' % os.path.basename(__file__))
        syslog.syslog(syslog.LOG_NOTICE, 'Service instantiated - platform %s' % service.platform)
        if service.distribution:
            syslog.syslog(syslog.LOG_NOTICE, 'Service instantiated - distribution %s' % service.distribution)

    rc = 0
    out = ''
    err = ''
    result = {}
    result['name'] = service.name
    result['state'] = service.state

    # Find service management tools
    service.get_service_tools()

    # Enable/disable service startup at boot if requested
    if service.module.params['enabled'] is not None:
        # FIXME: ideally this should detect if we need to toggle the enablement state, though
        # it's unlikely the changed handler would need to fire in this case so it's a minor thing.
        service.service_enable()

    # Collect service status
    if service.pattern:
        service.check_ps()
    service.get_service_status()

    # Calculate if request will change service state
    service.check_service_changed()

    # Modify service state if necessary
    (rc, out, err) = service.modify_service_state()

    if rc != 0:
        if err:
            module.fail_json(msg=err)
        else:
            module.fail_json(msg=out)

    result['changed'] = service.changed
    if service.module.params['enabled'] is not None:
        result['enabled'] = service.module.params['enabled']

    if not service.module.params['state']:
        status = service.get_service_status()
        if status is None:
            result['state'] = 'absent'
        elif status is False:
            result['state'] = 'started'
        else:
            result['state'] = 'stopped'
    else:
        # as we may have just bounced the service the service command may not
        # report accurate state at this moment so just show what we ran
        if service.module.params['state'] in ['started','restarted','running']:
            result['state'] = 'started'
        else:
            result['state'] = 'stopped'

    return module.exit_json(**result)

# this is magic, see lib/ansible/module_common.py

from newcommon import *


