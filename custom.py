from ansible.module_common import REPLACER

if __name__ == "__main__":
    import sys
    sys.argv.pop(0)
    if not sys.argv:
        print "missing library command name"
        raise SystemExit(1)

    lib = open("library/%s" % sys.argv[0]).read()
    if REPLACER not in lib:
        print "this is a strange file indeed"
        raise SystemExit(1)

    lib = lib.replace(REPLACER, "\nfrom newcommon import *\n")
    lib = lib.replace("\nmain()", "") #do not run the module

    new = "newlibrary/%s.py" % sys.argv[0]
    open(new, 'w').write(lib)
    print "wrote %r" % new

    from newlibrary import user
