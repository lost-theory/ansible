#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2012, Mark Theunissen <mark.theunissen@gmail.com>
# Sponsored by Four Kitchens http://fourkitchens.com.
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
module: mysql_db
short_description: Add or remove MySQL databases from a remote host.
description:
   - Add or remove MySQL databases from a remote host.
version_added: "0.6"
options:
  name:
    description:
      - name of the database to add or remove
    required: true
    default: null
  login_user:
    description:
      - The username used to authenticate with
    required: false
    default: null
  login_password:
    description:
      - The password used to authenticate with
    required: false
    default: null
  login_host:
    description:
      - Host running the database
    required: false
    default: localhost
  login_unix_socket:
    description:
      - The path to a Unix domain socket for local connections
    required: false
    default: null
  state:
    description:
      - The database state
    required: false
    default: present
    choices: [ "present", "absent", "dump", "import" ]
  collation:
    description:
      - Collation mode
    required: false
    default: null
  encoding:
    description:
      - Encoding mode
    required: false
    default: null
  target:
    description:
      - Where to dump/get the C(.sql) file
    required: false
examples:
   - code: "mysql_db: db=bobdata state=present"
     description: Create a new database with name 'bobdata'
notes:
   - Requires the MySQLdb Python package on the remote host. For Ubuntu, this
     is as easy as apt-get install python-mysqldb. (See M(apt).)
   - Both I(login_password) and I(login_user) are required when you are
     passing credentials. If none are present, the module will attempt to read
     the credentials from C(~/.my.cnf), and finally fall back to using the MySQL
     default login of C(root) with no password.
requirements: [ ConfigParser ]
author: Mark Theunissen
'''

import ConfigParser
import os
try:
    import MySQLdb
except ImportError:
    mysqldb_found = False
else:
    mysqldb_found = True

# ===========================================
# MySQL module specific support methods.
#

def db_exists(cursor, db):
    res = cursor.execute("SHOW DATABASES LIKE %s", (db,))
    return bool(res)

def db_delete(cursor, db):
    query = "DROP DATABASE %s" % db
    cursor.execute(query)
    return True

def db_dump(host, user, password, db_name, target):
    res = os.system("/usr/bin/mysqldump -q -h "+host+"-u "+user+ " -p"+password+" "
            +db_name+" > "
            +target)
    return (res == 0)

def db_import(host, user, password, db_name, target):
    res = os.system("/usr/bin/mysql -h "+host+" -u "+user+ " -p"+password+" "
            +db_name+" < "
            +target)
    return (res == 0)

def db_create(cursor, db, encoding, collation):
    if encoding:
        encoding = " CHARACTER SET %s" % encoding
    if collation:
        collation = " COLLATE %s" % collation
    query = "CREATE DATABASE %s%s%s" % (db, encoding, collation)
    res = cursor.execute(query)
    return True

def strip_quotes(s):
    """ Remove surrounding single or double quotes

    >>> print strip_quotes('hello')
    hello
    >>> print strip_quotes('"hello"')
    hello
    >>> print strip_quotes("'hello'")
    hello
    >>> print strip_quotes("'hello")
    'hello

    """
    single_quote = "'"
    double_quote = '"'

    if s.startswith(single_quote) and s.endswith(single_quote):
        s = s.strip(single_quote)
    elif s.startswith(double_quote) and s.endswith(double_quote):
        s = s.strip(double_quote)
    return s


def config_get(config, section, option):
    """ Calls ConfigParser.get and strips quotes

    See: http://dev.mysql.com/doc/refman/5.0/en/option-files.html
    """
    return strip_quotes(config.get(section, option))


def load_mycnf():
    config = ConfigParser.RawConfigParser()
    mycnf = os.path.expanduser('~/.my.cnf')
    if not os.path.exists(mycnf):
        return False
    try:
        config.readfp(open(mycnf))
    except (IOError):
        return False
    # We support two forms of passwords in .my.cnf, both pass= and password=,
    # as these are both supported by MySQL.
    try:
        passwd = config_get(config, 'client', 'password')
    except (ConfigParser.NoOptionError):
        try:
            passwd = config_get(config, 'client', 'pass')
        except (ConfigParser.NoOptionError):
            return False
    try:
        creds = dict(user=config_get(config, 'client', 'user'),passwd=passwd)
    except (ConfigParser.NoOptionError):
        return False
    return creds

# ===========================================
# Module execution.
#

def main(**params):
    module = AnsibleModule(params=params,
        argument_spec = dict(
            login_user=dict(default=None),
            login_password=dict(default=None),
            login_host=dict(default="localhost"),
            login_unix_socket=dict(default=None),
            db=dict(required=True, aliases=['name']),
            encoding=dict(default=""),
            collation=dict(default=""),
            target=dict(default=None),
            state=dict(default="present", choices=["absent", "present","dump", "import"]),
        )
    )

    if not mysqldb_found:
        module.fail_json(msg="the python mysqldb module is required")

    db = module.params["db"]
    encoding = module.params["encoding"]
    collation = module.params["collation"]
    state = module.params["state"]
    target = module.params["target"]

    # Either the caller passes both a username and password with which to connect to
    # mysql, or they pass neither and allow this module to read the credentials from
    # ~/.my.cnf.
    login_password = module.params["login_password"]
    login_user = module.params["login_user"]
    if login_user is None and login_password is None:
        mycnf_creds = load_mycnf()
        if mycnf_creds is False:
            login_user = "root"
            login_password = ""
        else:
            login_user = mycnf_creds["user"]
            login_password = mycnf_creds["passwd"]
    elif login_password is None or login_user is None:
        module.fail_json(msg="when supplying login arguments, both login_user and login_password must be provided")
    login_host = module.params["login_host"]

    if state in ['dump','import']:
        if target is None:
            module.fail_json(msg="with state=%s target is required" % (state))
        connect_to_db = db
    else:
        connect_to_db = 'mysql'
    try:
        if module.params["login_unix_socket"]:
            db_connection = MySQLdb.connect(host=module.params["login_host"], unix_socket=module.params["login_unix_socket"], user=login_user, passwd=login_password, db=connect_to_db)
        else:
            db_connection = MySQLdb.connect(host=module.params["login_host"], user=login_user, passwd=login_password, db=connect_to_db)
        cursor = db_connection.cursor()
    except Exception, e:
        module.fail_json(msg="unable to connect, check login_user and login_password are correct, or alternatively check ~/.my.cnf contains credentials")

    changed = False
    if db_exists(cursor, db):
        if state == "absent":
            changed = db_delete(cursor, db)
        elif state == "dump":
            changed = db_dump(login_host, login_user, login_password, db, target)
            if not changed:
                module.fail_json(msg="dump failed!")
        elif state == "import":
            changed = db_import(login_host, login_user, login_password, db, target)
            if not changed:
                module.fail_json(msg="import failed!")
    else:
        if state == "present":
            changed = db_create(cursor, db, encoding, collation)

    return module.exit_json(changed=changed, db=db)

# this is magic, see lib/ansible/module_common.py

from newcommon import *

