# yarss2imap
Yet another RSS2imap feed aggregator. Runs as a python IMAP client that pushes RSS items into IMAP folders.
Distributed under the GNU Affero General Public License v.3.0 (or later). Copyright 2016 Jean Millerat

# Here it goes

You can run the tests below with this command line :

    python3 main.py

or

    python3 main.py -v

We want to connect to IMAP server. Its parameters are to be stored in the config.py file. You should copy config.py.example to config.py and update its contents according to your environment.

    >>> import config
    >>> config.test
    'OK'

We should be able to connect to an IMAP account with these settings.

    >>> from main import Yarss2imapAgent
    >>> agent = Yarss2imapAgent()
    >>> agent.login()
    'OK'
    >>> agent.select()
    'OK'

And we can load an example feed from a local atom file.

    >>> import feedparser
    >>> stuff = feedparser.parse('akasig.atom')
    >>> stuff.feed.title
    'Jean, aka Sig(gg)'

import pdb ; pdb.set_trace()

# Logout from imap

    >>> agent.close()
    'OK'
    >>> agent.logout()
    'BYE'

