# yarss2imap
Yet another RSS2imap feed aggregator. Runs as a python IMAP client that pushes RSS items into IMAP folders.
Distributed under the GNU Affero General Public License v.3.0 (or later). Copyright 2016 Jean Millerat

# Here it goes

You can run the tests below with this command line :

    python3 -m doctest README.md

or, for more verbosity :

    python3 -m doctest README.md -v

# Configuration

We want to connect to IMAP server. Its parameters are to be stored in the config.py file.
You should copy config.py.example to config.py and update its contents according to your environment.

    >>> import config
    >>> config.test
    'OK'

We should be able to connect to an IMAP account with these settings.

    >>> from main import Yarss2imapAgent
    >>> agent = Yarss2imapAgent()
    >>> agent.login()
    'OK'

# Test setup

Let's remove any test mailbox left from previous tests.

    >>> agent.purge(mailbox='INBOX.testyarss2imap')
    'OK'

Let's create an empty test mailbox.

    >>> agent.select(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject ""')
    ('OK', [b''])
    >>> agent.list('INBOX.testyarss2imap')
    ('OK', [None])

We can load the example feed from my blog.

    >>> import feedparser
    >>> feed = feedparser.parse('http://www.akasig.org/feed/')
    >>> feed.feed.title
    'Jean, aka Sig(gg)'

# How to add feeds

You just have to send an email to your IMAP account.

    >>> import email.message
    >>> msg = email.message.Message()

The message must be from an authorized sender given in the config file.
The subject line of the message must start with "feed" then a whitespace then the URL of the feed, e.g. "feed http://www.akasig.org/feed/".

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

You then have to ask the agent for an update.
It creates an IMAP folder with this feed.

    >>> agent.list('INBOX.testyarss2imap')
    ('OK', [None])
    >>> agent.update(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> title = feed.feed.title
    >>> folders = agent.list('INBOX.testyarss2imap')[1] 
    >>> True in [title in folderName.decode() for folderName in folders]
    True

It moved the command message from the inbox to that new folder.

    >>> agent.select(mailbox='INBOX')
    'OK'
    >>> agent.uid('search', None, 'HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None], [b'']]
    True
    >>> agent.select(mailbox='"INBOX.testyarss2imap.' + title + '"')
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
    >>> subject_header = msg['Subject']
    >>> from email.header import decode_header
    >>> decoded_subject = decode_header(subject_header)[0]
    >>> decoded_subject[0].decode(decoded_subject[1]) == entry.title
    True

Its From line gives the author of the corresponding feed item.

    >>> msg['From'] == entry.author
    True

The URL of the corresponding feed item is stored as a X-Link field.

    >>> msg['X-Entry-Link'].split()[-1] == entry.link
    True

It has two parts.

    >>> len(msg.get_payload())
    2
    >>> part1, part2 = msg.get_payload()

First part is the plain text version of the feed entry.

    >>> part1.get_content_type()
    'text/plain'

Second part is the HTML version.

    >>> part2.get_content_type()
    'text/html'

The HTML version contains the feed item.

    >>> htmlFromEmail = part2.get_payload(decode=True).decode()
    >>> htmlFromFeed = entry.content[0]['value']
    >>> htmlFromFeed in htmlFromEmail
    True

Its body starts with the link to the corresponding feed item.

    >>> htmlFromEmail.split('Retrieved from')[0] == '<p><a href="' + entry.link + '">'
    True

The date of this feed items precedes the date the feed was updated.

    >>> msg['Date'] < feed.updated
    True

# Next update

Next time the agent updates...

    >>> agent.update(mailbox='INBOX.testyarss2imap')
    'OK'

There are as many items in that folder as before. No more, no less.

    >>> agent.select(mailbox='INBOX.testyarss2imap.' + title)
    'OK'
    >>> nbOfItems == len(agent.uid('search', None, 'HEADER Subject ""')[1][0].split())
    True

# Cleanup and logout 

    >>> agent.purge(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.close()
    'OK'
    >>> agent.logout()
    'BYE'

