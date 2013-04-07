import os
import sys

NEWLIBDIR = os.path.dirname(os.path.abspath(__file__))
_g = globals()
sys.path.append(os.path.join(NEWLIBDIR, ".."))

def dummy(*a, **kw):
    raise Exception("this module didn't load properly, probably due to an ImportError / missing dependency")

for name in os.listdir(NEWLIBDIR):
    if name in ["__init__.py", "newcommon.py"] or not name.endswith(".py"):
        continue
    name = name.replace(".py", "")

    #automatically import 'main' function from all modules with a fixed up name
    #i.e.: from user import main as user
    try:
        _g[name] = __import__("newlibrary.%s" % name, fromlist=[name]).main
    except Exception, e:
        '''
        if ("sys.exit" not in repr(e)
                and not isinstance(e, ImportError)):
            #not sure what this error was..
            raise
        '''
        print "problem with importing %r, missing a dependency? exception was %r" % (name, e)
        _g[name] = dummy
