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

There is an yarss2imap default folder in the INBOX.
But this agent knows no feed by default.
There is no IMAP folder for our example feed yet.

We can load the example feed from a local atom file.

    >>> import feedparser
    >>> feed = feedparser.parse('akasig.atom')
    >>> feed.feed.title
    'Jean, aka Sig(gg)'

Let's ask our agent to add this same feed by sending an email to this IMAP account.

    >>> import email.message
    >>> msg = email.message.Message()

The message is from an authorized sender given in the config file.
The subject line of the message contains the URL of the feed.

    >>> msg['From'] = config.authorizedSender
    >>> msg['Subject'] = 'feed ' + feed.feed.link
    >>> msg['Subject']
    'feed http://www.akasig.org'
    >>> import imaplib, time
    >>> status, data = agent.append('INBOX', '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    >>> status
    'OK'

Now the message is received by the agent.

    >>> status, data = agent.uid('search', None,'HEADER Subject "feed ' + feed.feed.link + '"') 
    >>> status
    'OK'

email.message_from_string(agent.fetch('1', '(RFC822)')[1][0][1].decode())['subject']

Now the agent knows that feed indicated in the message.

And there is an IMAP folder with this feed.
The folder contains as many items as there are items in this feed.
Each folder item is a message.
Let's have a look at one of these messages.
Its Subject: line is the title of the corresponding feed item.
Its From: line gives the author of the corresponding feed item.
Its body starts with the URL of the corresponding feed item.
Its body contains the content of the corresponding feed item.
It has as many attachments as the corresponding feed item.

# Logout from imap

    >>> agent.close()
    'OK'
    >>> agent.logout()
    'BYE'

