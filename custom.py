from ansible.module_common import REPLACER

if __name__ == "__main__":
    import sys
    sys.argv.pop(0)
    if not sys.argv:
        print "missing library command name"
        raise SystemExit(1)

    name = sys.argv[0]
    lib = open("library/%s" % name).read()
    if (REPLACER not in lib
            or "\nmain()" not in lib
            or "def main():" not in lib
            or "AnsibleModule(" not in lib):
        print "this is a strange file indeed"
        raise SystemExit(1)

    lib = lib.replace(REPLACER, "\nfrom newcommon import *\n") #replace boilerplate code with our new common code
    lib = lib.replace("\nmain()", "") #do not run the module
    lib = lib.replace("def main():", "def main(**params):") #replace main()'s signature
    lib = lib.replace("AnsibleModule(", "AnsibleModule(params=params,") #pass in params from main()'s new signature
    lib = lib.replace("module.exit_json", "return module.exit_json") #return output from main()

    new = "newlibrary/%s.py" % name
    open(new, 'w').write(lib)
    print "wrote %r" % new

    from newlibrary import user
