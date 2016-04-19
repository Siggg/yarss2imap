import imaplib
import config
import email, email.message, email.mime.multipart, email.mime.text
import re
import feedparser
import urllib.parse
import time
import sys
import html2text
import unicodedata
import logging
logging.basicConfig(filename=config.logfile, format='%(levelname)s:%(asctime)s %(message)s', level=logging.DEBUG)

class Yarss2imapAgent(imaplib.IMAP4):
    def __init__(self):
        logging.info("Initializing new agent.")
        try:
            imaplib.IMAP4_SSL.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4_SSL
        except:
            imaplib.IMAP4.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4

    def login(self):
        logging.info("Logging in.")
        status, message = self.IMAP.login(self, config.username, config.password)
        return status

    def select(self, mailbox='INBOX.' + config.mailbox):
        logging.info("Selecting mailbox: " + mailbox)
        mbox = unicodedata.normalize('NFKD', mailbox).encode('ASCII','ignore')
        if mailbox[0] != '"':
            mbox = '"' + mailbox + '"'
        status, message = self.IMAP.select(self, mbox)
        if status == 'NO': # there's no such mailbox, let's create one
           self.IMAP.select(self)
           status, msg = self.IMAP.create(self, mbox) 
           if status != "OK":
               logging.error("Could not create mailbox: " + mbox)
           self.IMAP.subscribe(self, mbox)
           status, message = self.IMAP.select(self, mbox)
           if status != "OK":
               logging.error("Could not select mailbox: " + mbox)
        return status 

    def close(self):
        logging.info("Closing connexion.")
        status, message = self.IMAP.close(self)
        return status

    def logout(self):
        logging.info("Logging out.")
        status, message = self.IMAP.logout(self)
        return status

    def purge(self, mailbox=None):
        """ Deletes given mailbox and its content. """
        if mailbox is None:
            return None
        logging.info("Erasing mailbox: " + mailbox)
        list = self.list(mailbox)[1]
        self.select(mailbox='INBOX')
        for line in list:
            if line is None:
                continue
            line = line.decode()
            path = re.search('\(.*\) ".*" "(.*)"', line).groups()[0]
            if path[0] != '"':
                path = '"' + path + '"'
            status, msg = self.unsubscribe(path)
            if status != 'OK':
                logging.error("Could not unsubscribe from: " + path)
            status, msg = self.delete(path)
            if status != 'OK':
                logging.error("Could not delete path: " + path)
        self.unsubscribe(mailbox)
        self.delete(mailbox)
        return 'OK'

    def moveUID(self, uid, fromMailbox='INBOX', toMailbox='INBOX'):
        if fromMailbox == toMailbox or '"' + fromMailbox + '"' == toMailbox :
            return
        logging.info("Moving message from " + fromMailbox + " to " + toMailbox)
        self.select(fromMailbox)
        self.uid('copy', uid, toMailbox)
        self.uid('store', uid, '+FLAGS', '\\Deleted')

    def update(self, mailbox='INBOX.' + config.mailbox):
        logging.info("Updating mailbox: " + mailbox)

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
            logging.info("Looking for command messages in: " + mb)
            self.select(mb)
            self.recent()
            status, data = self.uid('search', None, 'HEADER Subject "feed "')
            uids = data[0].decode().split()
            logging.info("Found " + str(len(uids)) + " feed messages in mailbox: " + mb)
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

        logging.info("Updating " + str(len(feeds.keys())) + " feed(s).")
        # Now back to our mailbox
        for url in feeds.keys():

            logging.info("Updating feed from URL: " + url)
            # Create a folder for that feed
            feed = feedparser.parse(url)
            title = 'No title'
            try:
                title = feed.feed.title
            except AttributeError:
                pass
            # path = mailbox + '.' + urllib.parse.quote_plus(title)
            title = unicodedata.normalize('NFKD', title).encode('ASCII','ignore')
            path = '"' + mailbox + '.' + title.decode().replace("/","?").replace(".","-") + '"'
            logging.info("Creating mailbox path: " + path)
            self.select(mailbox=mailbox)
            self.create(path) 
            self.subscribe(path)
            
            # Move corresponding command messages from INBOX to that new folder
            for mb, uid in feeds[url]:
                self.moveUID(uid, fromMailbox=mb, toMailbox=path)
            self.select(mailbox=mb)
            self.expunge()

            # Create one message per feed item
            logging.info("Examining " + str(len(feed.entries)) + " feed entries.")
            for entry in feed.entries:
                # Is there already a message for this entry ?
                status, data = self.uid('search', None, 'HEADER X-Entry-Link "' + entry.link + '"')
                if data[0] not in [None, b'']:
                    # There is already one, move on !
                    continue
                logging.info("Creating message about: " + entry.title)
                msg = email.mime.multipart.MIMEMultipart('alternative')
                msg.set_charset(feed.encoding)
                msg['From'] = entry.author
                msg['Subject'] = entry.title
                msg['To'] = config.username
                msg['Date'] = entry.published
                msg['X-Entry-Link'] = entry.link
                try:
                    content = entry.content[0]['value']
                except AttributeError:
                    try:
                        content = entry.summary
                    except AttributeError:
                        content = entry.description
                html = '<p><a href="' + entry.link + '">Retrieved from ' + entry.link + '</a></p>'
                html += content
                text = html2text.html2text(html)
                part1 = email.mime.text.MIMEText(text, 'plain')
                part2 = email.mime.text.MIMEText(html, 'html')
                msg.attach(part1)
                msg.attach(part2)
                # msg.set_payload(text, feed.encoding)
                
                self.append(path, '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())

        return 'OK'

    def loop(self):
        logging.info("Agent starting loop.")
        try:
            while True:
                self.update()
                logging.info("Sleeping for 60 seconds.")
                time.sleep(60)
        except:
            logging.warning("Unexpected error: %s" % sys.exc_info()[0])
        logging.info("Agent stopping loop.")

if __name__ == "__main__":
    agent = Yarss2imapAgent()
    agent.login()
    agent.select()
    agent.loop()
    agent.close()
    agent.logout()
