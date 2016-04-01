# yarss2imap
Yet another RSS2imap feed aggregator. Runs as a python IMAP client that pushes RSS items into IMAP folders.
Distributed under the GNU Affero General Public License v.3.0 (or later). Copyright 2016 Jean Millerat

# Here it goes

    >>> 'hello'
    'hello'

We want to connect to IMAP server. Its parameters are to be stored in the config.py file. You should copy config.py.example to config.py and update its contents according to your environment.

    >>> import config
    >>> config.test
    'OK'

We should be able to connect to an IMAP account with these settings.

    >>> import imaplib
    >>> M = imaplib.IMAP4(config.servername,config.port)
    >>> status, message = M.login(config.username,config.password)
    >>> status
    'OK'
