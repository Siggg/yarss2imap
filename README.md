# yarss2imap

Welcome there ! This is Yet another RSS2imap feed aggregator. It runs as a python IMAP client that pushes RSS items into IMAP folders.

Please drop me an email to say hello or tell me your thoughts about this piece of software : sig at akasig dot org

Distributed under the GNU Affero General Public License v.3.0 (or later). Copyright 2016 Jean Millerat. See the license section below for more information.

# Quickstart

Copy config.py.example and rename it into config.py
Edit config.py according to your IMAP settings.
Then run the client

    python3 main.py

# Documented test

BEWARE : running these tests may delete messages in your 'INBOX' mailbox. It will delete messages if their
subject line is "importOPML" or starts with "feed ".

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

    >>> from main import YAgent
    >>> agent = YAgent()
    >>> agent.login()
    'OK'

# Test setup

Let's remove messages titled "importOPML" or "feed " from the INBOX. You had been warned !

    >>> agent.select('INBOX')
    'OK'
    >>> status, data = agent.imap.uid('search', None, 'UNDELETED HEADER Subject "importOPML"') 
    >>> uids = data[0].decode().split()
    >>> status, data = agent.imap.uid('search', None, 'UNDELETED HEADER Subject "feed "')
    >>> uids += data[0].decode().split()
    >>> for uid in uids: 
    ...     status, data = agent.imap.uid('store', uid, '+FLAGS', '\\Deleted')

Let's remove any test mailbox left from previous tests.

    >>> result = agent.purge(mailbox='INBOX.testyarss2imap')

Let's create an empty test mailbox.

    >>> agent.select(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.imap.uid('search', None, 'HEADER Subject ""')
    ('OK', [b'1'])
    >>> agent.imap.list('INBOX.testyarss2imap')[0]
    'OK'

It's not empty because it was populated with a README message at creation.

    >>> subject = agent.imap.uid('fetch', '1', '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1].decode()
    >>> 'Welcome to yarss2imap' in subject
    True

We can load the example feed from my blog.

    >>> import feedparser
    >>> feed = feedparser.parse('http://www.akasig.org/feed/')
    >>> feed.feed.title
    "Jean Millerat's bytes for good"

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
    >>> status, data = agent.imap.append('INBOX', '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    >>> status
    'OK'

Now the message is received by the agent.

    >>> agent.select(mailbox='INBOX')
    'OK'
    >>> agent.imap.uid('search', None, 'HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None],[b'']]
    False

You then have to ask the agent for an update.
It creates an IMAP folder with this feed.

    >>> agent.imap.list('INBOX.testyarss2imap')[0]
    'OK'
    >>> agent.update(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> title = feed.feed.title
    >>> folders = agent.imap.list('INBOX.testyarss2imap')[1]
    >>> folders[-1].decode().split('"')[-2]
    "INBOX.testyarss2imap.Jean Millerat's bytes for good"

It moved the command message from the inbox to that new folder.

    >>> agent.select(mailbox='INBOX')
    'OK'
    >>> agent.imap.uid('search', None, 'UNDELETED HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None], [b'']]
    True
    >>> agent.select(mailbox='"INBOX.testyarss2imap.' + title + '"')
    'OK'
    >>> agent.imap.uid('search', None, 'UNDELETED HEADER Subject "feed ' + feed.feed.links[0].href + '"')[1] in [[None], [b'']]
    False

The folder contains more items than how many there are in this feed.

    >>> nbOfItems = len(agent.imap.uid('search', None, 'ALL')[1][0].split())
    >>> nbOfItems > len(feed.entries)
    True

Each folder item is a message.
Let's have a look at one of these messages.
Its Subject line is the title of the corresponding feed item.

    >>> msgBin = agent.imap.uid('fetch', b'2', '(RFC822)')[1][0][1]
    >>> msg = email.message_from_bytes(msgBin)
    >>> subject_header = msg['Subject']
    >>> from email.header import decode_header
    >>> decoded_subject = decode_header(subject_header)[0]
    >>> entry = feed.entries[0]
    >>> decoded_subject[0].decode(decoded_subject[1]) == entry.title
    True

Its From line gives the author of the corresponding feed item and the feed title.

    >>> msg['From'] == entry.author + ' @ ' + feed.feed.title
    True

The URL of the corresponding feed item is stored as a X-Entry-Link field.

    >>> from email.header import decode_header, make_header
    >>> header = str(make_header(decode_header(msg['X-Entry-Link'])))
    >>> header == entry.link
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

Its body ends with the link to the corresponding feed item.

    >>> htmlFromEmail.split('Retrieved from ')[-1] == entry.link + '</a></p>'
    True

The date of this feed items precedes the date the feed was updated.

# Next update

Next time the agent updates...

    >>> agent.update(mailbox='INBOX.testyarss2imap')
    'OK'

There are as many items in that folder as before. No more, no less.

    >>> agent.select(mailbox='INBOX.testyarss2imap.' + title)
    'OK'
    >>> nbOfItems == len(agent.imap.uid('search', None, 'ALL')[1][0].split())
    True

# OPML import

    We have a local example of an OPML file (downloaded from http://www.howtocreate.co.uk/tutorials/jsexamples/sampleOPML.xml).

    >>> f = open('sampleOPML.xml','rt')
    >>> from xml.etree import ElementTree
    >>> opml = f.read()
    >>> root = ElementTree.fromstring(opml)
    
    There are 3 OPML outlines there.

    >>> len(root.findall('.//outline'))
    3

    Our agent can import this OPML file. It then creates one new mailbox per OPML outline.

    >>> mailboxesBefore = agent.imap.list('INBOX.testyarss2imap')[1]
    >>> from main import YImportCommandMessage
    >>> opmlCommandMessage = YImportCommandMessage(message=None, mailbox=None, messageUID=None, agent=agent)
    >>> opmlCommandMessage.opml = opml
    >>> opmlCommandMessage.execute(underMailbox='INBOX.testyarss2imap')
    'OK'
    >>> mailboxesAfter = agent.imap.list('INBOX.testyarss2imap')[1]
    >>> newMailboxes = [mailbox for mailbox in mailboxesAfter if mailbox not in mailboxesBefore]
    >>> len(newMailboxes)
    3

    There are 3 outlines with an XML URL in this OPML example file. Each outline with an XML URL got its "feed" message.

    >>> outlines = root.findall('.//outline[@xmlUrl]')
    >>> urls = [outline.get('xmlUrl') for outline in outlines]
    >>> len(urls)
    3
    >>> import re # get ready for mailbox names extraction
    >>> newMailboxes = ['"' + re.search('\(.*\) ".*" "(.*)"', mb.decode()).groups()[0] + '"' for mb in newMailboxes]
    >>> for mailbox in newMailboxes:
    ...     result = agent.select(mailbox)
    ...     status, data = agent.imap.uid('search', None, 'HEADER Subject "feed "')
    ...     if len(data[0]) > 0:
    ...         print("Found")
    Found
    Found
    Found

    So far so good for importing an OPML file using the API. But we can import OPML files via a command message, too.
    Let's retry this way and start with erasing our newly created mailboxes.

    >>> for mailbox in newMailboxes:
    ...     agent.purge(mailbox)
    'OK'
    'OK'
    'OK'

    Feed messages for theses mailboxes have disappeared.

    >>> for mailbox in newMailboxes:
    ...     result = agent.select(mailbox)
    ...     status, data = agent.imap.uid('search', None, 'HEADER Subject "feed "')
    ...     if len(data[0]) > 0:
    ...         print("Found")

    Our command message must be titled 'importOPML' and have the OPML file as an attachment.

    >>> msg = email.mime.multipart.MIMEMultipart()
    >>> msg['From'] = config.authorizedSender
    >>> msg['Subject'] = 'importOPML'
    >>> msg['To'] = config.authorizedSender
    >>> msg.preamble = 'OPML file to be imported'
    >>> opmlFile  = f
    >>> opmlFile.seek(0)
    0
    >>> opmlPart = email.mime.text.MIMEText(opmlFile.read(), 'xml')
    >>> msg.attach(opmlPart)
    >>> status, data = agent.imap.append('INBOX', '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    >>> status
    'OK'

    The feed messages corresponding to the OPML outlines contained in this file do reappear at the next update.

    >>> agent.update(mailbox = 'INBOX.testyarss2imap')
    'OK'
    >>> for mailbox in newMailboxes:
    ...     result = agent.select(mailbox)
    ...     status, data = agent.imap.uid('search', None, 'HEADER Subject "feed "') 
    ...     if len(data[0]) > 0:
    ...         print("Found")
    Found
    Found
    Found

# Cleanup and logout 

    >>> agent.purge(mailbox='INBOX.testyarss2imap')
    'OK'
    >>> agent.close()
    'OK'
    >>> agent.logout()
    'BYE'

# License

GNU Affero General Public License (AGPL)

Copyright (c) 2016 by Jean Millerat, 76 avenue de Beaujeu, 78990 ELANCOURT (sig at akasig dot org)

This file is part of a program which is free software : you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.

If not, see http://www.gnu.org/licenses/ 

# Features being considered for some future version

It would be great if the following features existed, wouldn't it be ?

- when first started, a welcome/help message is generated and placed into the INBOX, with an invitation to let Siggg know about what you think about yarss2imap

- a "diff http://" command allows this URL to be monitored and text diffs (diffs using html2text and diff) are posted as messages with the HTML attached for historical reference

- error messages are posted in case a feed can't be updated.

- connection nicely restarts after inactivity and an imaplib.IMAP4.abort exception

- Siggg's magical feed sorting scheme gets implemented

- attachments to feed entries (think podcast) become attachments to messages

- email newsletters get sorted into folders named according to some extraction from the "From:" field of messages

- this package is distributed as a Windows executable with the configuration file as an .ini file

- if the URL of a feed command can't be parsed as a valid RSS or atom file, alternative RSS or atom links are searched in this HTML
	and these links are posted in the body of the feed message with an \Unseen flag set for a notice

- a "twitter @siggg" command allows @siggg's tweets to be monitored and posted as messages

- a "facebook Jean.Millerat" command allows Jean.Millerat's posts on his Facebook wall to be monitored and posted as messages

- a "reddit /r/aww" command allows the aww subreddit to be monitored (also "reddit /u/jeanAkaSiggg")

- multithreading and timeouts are used to optimize the duration of updates

- feed that didn't get updates for several years get a warning message

- alerts are generated whenever the mailbox size is about to be reached

- the feed command message gets the date of the latest update. 

