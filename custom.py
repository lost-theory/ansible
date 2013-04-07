import os

REPLACER = "#<<INCLUDE_ANSIBLE_MODULE_COMMON>>"

def transform(name):
    lib = open("library/%s" % name).read()
    if (REPLACER not in lib
            or "\nmain()" not in lib
            or "def main():" not in lib
            or "AnsibleModule(" not in lib):
        raise ValueError("%r is a strange file indeed" % lib)

    lib = lib.replace(REPLACER, "\nfrom newcommon import *\n") #replace boilerplate code with our new common code
    lib = lib.replace("\nmain()", "") #do not run the module
    lib = lib.replace("def main():", "def main(**params):") #replace main()'s signature
    lib = lib.replace("AnsibleModule(", "AnsibleModule(params=params,") #pass in params from main()'s new signature

    #send return values instead of relying on *_json functions to write to stdout / call sys.exit
    lib = lib.replace("self.module.exit_json", "__rsmej__")
    lib = lib.replace("return module.exit_json", "__rmej__")
    lib = lib.replace("module.exit_json", "return module.exit_json")
    lib = lib.replace("m.exit_json", "return m.exit_json")
    lib = lib.replace("__rsmej__", "return self.module.exit_json")
    lib = lib.replace("__rmej__", "return module.exit_json")

    #replace sys.exit(1) with an exception that can be caught
    lib = lib.replace("sys.exit(1)", "raise Exception('was going to call sys.exit(1)') #XXX")

    #replace sys.exit(0) calls with print statement
    lib = lib.replace("sys.exit(0)", "print 'OK, was going to call sys.exit(0)' #XXX")

    #rename selinux module since it confuses the HAVE_SELINUX check
    newname = name
    if newname == "selinux":
        newname = "selinux_module"

    new = "newlibrary/%s.py" % newname
    open(new, 'w').write(lib)
    print "wrote %r" % new

def transform_all():
    libs = sorted(os.listdir("./library/"))
    stats = dict(converted=0, skipped=0)
    for l in libs:
        try:
            transform(l)
            stats['converted'] += 1
        except ValueError, e:
            if "strange file indeed" in repr(e):
                print "skipped %r because it looks strange" % l
                stats['skipped'] += 1
                continue
            raise
    print "done: %r" % stats

if __name__ == "__main__":
    import sys
    sys.argv.pop(0)
    if not sys.argv:
        print "missing library command name or 'all'"
        raise SystemExit(1)
    name = sys.argv[0]

    if name == "all":
        transform_all()
    else:
        transform(name)
