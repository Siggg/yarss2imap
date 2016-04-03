import imaplib
import config
import email, email.message
import re
import feedparser
import urllib.parse
import time

class Yarss2imapAgent(imaplib.IMAP4):
    def __init__(self):
        try:
            imaplib.IMAP4_SSL.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4_SSL
        except:
            imaplib.IMAP4.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4

    def login(self):
        status, message = self.IMAP.login(self, config.username, config.password)
        return status

    def select(self, mailbox='INBOX.' + config.mailbox):
        status, message = self.IMAP.select(self, mailbox)
        if status == 'NO': # there's no INBOX.yarss2imap mailbox yet, let's create one
           self.IMAP.select(self)
           self.IMAP.create(self, mailbox) 
           self.IMAP.subscribe(self, mailbox)
           status, message = self.IMAP.select(self, mailbox)
        return status 

    def close(self):
        status, message = self.IMAP.close(self)
        return status

    def logout(self):
        status, message = self.IMAP.logout(self)
        return status

    def purge(self, mailbox=None):
        if mailbox is None:
            return None
        list = self.list(mailbox)[1]
        self.select(mailbox='INBOX')
        for line in list:
            line = line.decode()
            path = re.search('\(.*\) ".*" "(.*)"', line).groups()[0]
            self.unsubscribe(path)
            self.delete(path)
        self.unsubscribe(mailbox)
        self.delete(mailbox)
        return 'OK'

    def moveUID(self, uid, fromMailbox='INBOX', toMailbox='INBOX'):
        self.select(fromMailbox)
        self.uid('copy', uid, toMailbox)
        self.uid('store', uid, '+FLAGS', '\\Deleted')

    def update(self, mailbox='INBOX.' + config.mailbox):
        # Did we receive any new command message in the INBOX or in the given mailbox ?
        mailboxes = ['INBOX', mailbox]
        # Or are there older command messages already stored under their own folders ?
        mbs = self.list(mailbox)[1]
        for mb in mbs:
            if mb is not None:
                mailboxName = re.search('\(.*\) ".*" "(.*)"', mb.decode()).groups()[0]
                mailboxes.append(mailboxName)

        # Search for such messages and their command line in those mailboxes
        subjectFromUIDs = {}
        for mb in mailboxes:
            self.IMAP.select(self, mb)
            self.recent()
            status, data = self.uid('search', None, 'HEADER Subject "feed "')
            uids = data[0].decode().split()
            for uid in uids:
                msgBin = self.uid('fetch', uid, '(RFC822)')[1][0][1]
                msg = email.message_from_bytes(msgBin)
                subjectFromUIDs[(mb,uid)] = msg['Subject']

        # Build the list of feed URL to be checked for new items
        feeds = {}
        for msgPath, subject in subjectFromUIDs.items():
            feedURL = re.search('feed (.*)', subject).groups()[0]

            # store the message mailbox and uid under this URL
            if feedURL not in feeds.keys():
                 feeds[feedURL] = []
            feeds[feedURL].append(msgPath)

        # Now back to our mailbox
        for url in feeds.keys():

            # Create a folder for that feed
            feed = feedparser.parse(url)
            title = 'No title'
            try:
                title = feed.feed.title
            except AttributeError:
                pass
            path = mailbox + '.' + urllib.parse.quote_plus(title)
            self.select(mailbox=mailbox)
            self.create(path) 
            self.subscribe(path)
            
            # Move corresponding command messages from INBOX to that new folder
            for mb, uid in feeds[url]:
                self.moveUID(uid, fromMailbox=mb, toMailbox=path)
            self.select(mailbox=mb)
            self.expunge()

            # Create one message per feed item
            for entry in feed.entries:
                # Is there already a message for this entry ?
                status, data = self.uid('search', None, 'HEADER X-Entry-Link "' + entry.link + '"')
                if data[0] not in [None, b'']:
                    # There is already one, move on !
                    continue
                msg = email.message.Message()
                msg['From'] = entry.author
                msg['Subject'] = entry.title
                msg['To'] = config.username
                msg['Date'] = entry.published
                msg['X-Entry-Link'] = entry.link
                msg.set_payload(entry.link + '\n' + entry.content[0]['value'], feed.encoding)
                
                self.append(path, '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())

        return 'OK'


if __name__ == "__main__":
    import doctest
    doctest.testfile("README.md")
