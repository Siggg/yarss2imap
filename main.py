import imaplib
import config
import email
import re
import feedparser
import urllib.parse

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

    def update(self,mailbox='INBOX.' + config.mailbox):
        # Did we receive any new command message ?
        self.IMAP.select(self,'INBOX')
        self.recent()
        status, data = self.uid('search', None,'HEADER Subject "feed "')
        feeds = {}
        for uid in data[0].decode().split():  # for each feed to be added
            # let's get its URL
            msgStr = self.uid('fetch',uid,'(RFC822)')[1][0][1].decode()
            msg = email.message_from_string(msgStr)
            subject = msg['subject']
            feedURL = re.search('feed (.*)', subject).groups()[0]
            feeds[feedURL] = None
        # Now back to our mailbox
        self.select(mailbox=mailbox)
        for url in feeds.keys():
            # Let's create a folder for that feed
            feed = feedparser.parse(url)
            title = 'No title'
            try:
                title = feed.feed.title
            except AttributeError:
                pass
            path = mailbox + '.' + urllib.parse.quote_plus(title)
            self.create(path) 
            self.subscribe(path)


if __name__ == "__main__":
    import doctest
    doctest.testfile("README.md")
