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
    lib = lib.replace("module.exit_json", "return module.exit_json")
    lib = lib.replace("m.exit_json", "return m.exit_json")
    lib = lib.replace("__rsmej__", "return self.module.exit_json")

    new = "newlibrary/%s.py" % name
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
