'''
Demo of using ansible modules as python modules that can be imported and run
as normal python code.

Example run and output:

    $ sudo python demo.py
    creating a bunch of stuff using the modules... done.
    verify all are True:
    * redteam in group file? True
    * blueteam in group file? True
    * joeshmoe exists? True
    * joeshmoe in redteam group? True
    * joeshmoe in blueteam group? True
    * ASCII rabbit exists? True
    * ASCII rabbit has eyes? True
    * joeshmoe has the cron job? True
    Press Enter to continue. Ctrl+C to quit.
    undoing what we just did... done.
    verify all are False:
    * redteam in group file? False
    * blueteam in group file? False
    * joeshmoe exists? False
    * joeshmoe in redteam group? False
    * joeshmoe in blueteam group? False
    * ASCII rabbit exists? False
    * ASCII rabbit has eyes? False
    * joeshmoe has the cron job? False
    Press Enter to continue. Ctrl+C to quit.
    congrats, it worked.
'''

import commands

from newlibrary import (
    user as User,
    group as Group,
    get_url as URL,
    ping as Ping,
    cron as Cron,
    file as File,
)

def run_demo():
    p = Ping()

    g1 = Group(name="redteam")
    g2 = Group(name="blueteam")
    u = User(name="joeshmoe", shell="/bin/sh", groups="redteam,blueteam")

    url = URL(
        url="https://gist.github.com/anonymous/5283202/raw/8431a8f46609bbdf1b31d5b0b17f76b9780dd13a/gistfile1.txt",
        dest="/etc/rabbit.txt",
        mode="0644",
    )

    c = Cron(
        name="testing cron stuff",
        job="date > /tmp/crontest.txt",
        minute="*",
        user="joeshmoe",
    )

def verify():
    print "* redteam in group file?", "redteam" in open("/etc/group").read()
    print "* blueteam in group file?", "blueteam" in open("/etc/group").read()
    print "* joeshmoe exists?", "joeshmoe" in open("/etc/passwd").read()
    print "* joeshmoe in redteam group?", "redteam" in commands.getoutput("groups joeshmoe")
    print "* joeshmoe in blueteam group?", "blueteam" in commands.getoutput("groups joeshmoe")
    print "* ASCII rabbit exists?", "rabbit.txt" in commands.getoutput("ls /etc")
    print "* ASCII rabbit has eyes?", "o. o" in commands.getoutput("grep o..o /etc/rabbit.txt")
    print "* joeshmoe has the cron job?", "testing cron stuff" in commands.getoutput("crontab -l -u joeshmoe")

def undo_demo():
    c = Cron(name="testing cron stuff", user="joeshmoe", state="absent")
    u = User(name="joeshmoe", state="absent")
    f = File(path="/etc/rabbit.txt", state="absent")
    g1 = Group(name="redteam", state="absent")
    g2 = Group(name="blueteam", state="absent")

if __name__ == "__main__":
    print "creating a bunch of stuff using the modules...",
    run_demo()
    print "done.\nverify all are True:"
    verify()
    raw_input("Press Enter to continue. Ctrl+C to quit.")
    print "undoing what we just did...",
    undo_demo()
    print "done.\nverify all are False:"
    verify()
    raw_input("Press Enter to continue. Ctrl+C to quit.")
    print "congrats, it worked."
