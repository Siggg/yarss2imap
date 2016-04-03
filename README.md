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

Let's create an empty test mailbox.

    >>> agent.select(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject ""')
    ('OK', [b''])
    >>> agent.list('INBOX.testyarss2imap')
    ('OK', [None])

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
    >>> msg['Subject'] = 'feed ' + feed.feed.links[0].href
    >>> msg['Subject']
    'feed http://www.akasig.org/feed/'
    >>> import imaplib, time
    >>> status, data = agent.append('INBOX', '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    >>> status
    'OK'

Now the message is received by the agent.

    >>> agent.select(mailbox='INBOX')
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None],[b'']]
    False

The agent created an IMAP folder with this feed.

    >>> agent.list('INBOX.testyarss2imap')
    ('OK', [None])
    >>> agent.update(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> import urllib.parse
    >>> title = urllib.parse.quote_plus('Jean, aka Sig(gg)')
    >>> folders = agent.list('INBOX.testyarss2imap')[1] 
    >>> True in [title in folderName.decode() for folderName in folders]
    True

It moved the command message from the in inbox to that new folder.

    >>> agent.select(mailbox='INBOX')
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None], [b'']]
    True
    >>> agent.select(mailbox='INBOX.testyarss2imap.' + title)
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None], [b'']]
    False

The folder contains more items than how many there are in this feed.

    >>> nbOfItems = len(agent.uid('search', None, 'HEADER Subject ""')[1][0].split())
    >>> nbOfItems > len(feed.entries)
    True

Each folder item is a message.
Let's have a look at one of these messages.
Its Subject line is the title of the corresponding feed item.

    >>> msgId = agent.uid('search', None, 'HEADER From "Sig"')[1][0].split()[-1]
    >>> msgBin = agent.uid('fetch', b'2', '(RFC822)')[1][0][1]
    >>> msg = email.message_from_bytes(msgBin)
    >>> entry = feed.entries[0]
    >>> msg['Subject'] == entry.title
    True

Its From line gives the author of the corresponding feed item.

    >>> msg['From'] == entry.author
    True

The URL of the corresponding feed item is stored as a X-Link field.

    >>> msg['X-Entry-Link'].split()[-1] == entry.link
    True

Its body starts with the URL of the corresponding feed item.

    >>> msg.get_payload().split('\r\n')[0][:75] == entry.link[:75]
    True

Its body contains the content of the corresponding feed item.

    >>> len(msg.get_payload()) > len(entry.link) + len(entry.content[0]['value'])
    True

Its date corresponds to the date the feed was published.

    >>> msg['Date']
    'Mon, 14 Mar 2016 08:32:00 +0000'


# Cleanup and logout 

    >>> agent.purge(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.close()
    'OK'
    >>> agent.logout()
    'BYE'

