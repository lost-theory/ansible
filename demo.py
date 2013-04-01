from newlibrary import user, group, get_url, ping, cron

def main():
    g1 = group(name="redteam")
    g2 = group(name="blueteam")
    u = user(name="joeshmoe", shell="/bin/sh", groups="redteam,blueteam")

    url = get_url(
        url="https://gist.github.com/anonymous/5283202/raw/8431a8f46609bbdf1b31d5b0b17f76b9780dd13a/gistfile1.txt",
        dest="/etc/rabbit.txt",
        mode="0644",
    )

    p = ping()

    c = cron(
        name="testing cron stuff",
        job="date > /tmp/crontest.txt",
        minute="*",
        user="steve",
    )

if __name__ == "__main__":
    main()
