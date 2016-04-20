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
from xml.etree import ElementTree

class YFeed():

    def __init__(self, url=None):
        self.url = url
        self.feed = None
        if url is not None:
            self.feed = feedparser.parse(url)


    def title(self, title = None):
        """ Returns the title of the feed. """

        if title is not None:
            self._title = title
        if hasattr(self, '_title'):
            return self._title
        self._title = 'No title'
        try:
            self._title = self.feed.feed.title
        except AttributeError:
            pass
        return self._title


    def safeTitle(self):

        if hasattr(self, '_safeTitle'):
            return self._safeTitle
        self._safeTitle = unicodedata.normalize('NFKD', self.title()).encode('ASCII','ignore')
        self._safeTitle = self._safeTitle.decode().replace("/","?").replace(".","-")
        return self._safeTitle


    def path(self, commandPaths = [], agent = None, mailbox = 'INBOX.' + config.mailbox):
        """ Returns the path of the mailbox associated with this feed. """

        if hasattr(self, '_path'):
            return self._path
        if agent is None:
            return None

        # Several mailboxes may contain a "feed" command with the URL of this feed.
        # The one with the longest path is the one to be associated with this feed.
        # Unless it is the main mailbox, then we are to look for one based on a matching name.
        longestPath = mailbox
        for path in commandPaths:
            if len(path) > len(longestPath):
                longestPath = path
        self._path = longestPath
        if self._path != mailbox:
            if self._path[0] != '"':
                self._path = '"' + self._path + '"'
            return self._path

        # OK. So. No matching mailbox with a "feed" command for the URL of this feed.
        # Does this feed have a mailbox with a name matching its title ?
        paths = agent.listMailboxes(mailbox, pattern='"*' + self.safeTitle() + '"')
        if len(paths) == 0: # no mailbox with that name, let's create one
            path = '"' + mailbox + '.' + self.safeTitle() + '"' 
            logging.info("Creating mailbox path: " + path)
            agent.select(mailbox=mailbox)
            agent.create(path)
            agent.subscribe(path)
        else:
            path = '"' + paths[0] +'"'
        self._path = path
        if self._path[0] != '"':
            self._path = '"' + self._path + '"'
        return self._path


    def updateEntries(self, agent = None, mailbox = 'INBOX.' + config.mailbox):
    
        if agent is None:
            return

        path = self.path(agent = agent, mailbox = mailbox)

        # Create one message per feed item
        logging.info("Examining " + str(len(self.feed.entries)) + " feed entries.")
        agent.select(mailbox = path)
        for entry in self.feed.entries:

            # Is there already a message for this entry ?
            status, data = agent.uid('search', None, 'HEADER X-Entry-Link "' + entry.link + '"')
            if data[0] not in [None, b'']:
                # There is already one, move on !
                continue

            logging.info("Creating message about: " + entry.title)
            msg = email.mime.multipart.MIMEMultipart('alternative')
            msg.set_charset(self.feed.encoding)
            try:
                msg['From'] = entry.author
            except AttributeError:
                msg['From'] = self.title()
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

            status, error = agent.append(path, '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            if status != 'OK':
                 logging.error('Could not append message, with this error message: ' + error)


    def createMailbox(self, agent = None, parentMailbox = 'INBOX.' + config.mailbox):
        """ Creates a mailbox with a given name and a command message for a feed at the given URL.
            If no name but a URL is given, the name is the title of feed at this URL.
            If no URL but a name is given, the mailbox is created without any command message."""
                                
        logging.info("Creating a feed mailbox named '" + self.title() + "' and this URL: " + str(self.url))
        if self.url is None and self.title() is None:
            logging.error('Could not create mailbox without a feed nor a name.')
        if agent is None:
            logging.error('Could not create mailbox without an IMAP agent: ' + str(self.url))
        path = '"' + parentMailbox.strip('"') + '.' + self.safeTitle() + '"'
        agent.select(mailbox = path)
        if self.url is None:
            return path
        msg = email.mime.text.MIMEText("", "plain")
        msg['Subject'] = "feed " + str(self.url)
        msg['From'] = config.authorizedSender
        msg['To'] = config.authorizedSender
        status, error = agent.append(path, '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if status != 'OK':
            logging.error('Could not append message, with this error message: ' + error)
        return path



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

        fromMb = fromMailbox
        if fromMb[0] != '"':
            fromMb = '"' + fromMb + '"' # make it safe
        toMb = toMailbox
        if toMb[0] != '"':
            toMb = '"' + toMb + '"' # make it safe
        if fromMb == toMb:
            return
        logging.info("Moving message from " + fromMb + " to " + toMb)
        status = self.select(fromMb)
        if status != 'OK':
            logging.error("Could not select mailbox: " + fromMb)
        status, msg = self.uid('copy', uid, toMb)
        if status != 'OK':
            logging.error("Could not copy a message to mailbox: " + toMb)
            logging.error("   error message was: " + msg)
        status, msg = self.uid('store', uid, '+FLAGS', '\\Deleted')
        if status != 'OK':
            logging.error("Could not delete message with UID: " + uid)
            logging.error("   error message was: " + msg)


    def listMailboxes(self, mailbox='INBOX' + config.mailbox, pattern='*'):
        """ lists mailbox paths under given mailbox and with names matching given pattern. """

        mailboxes = []
        mbs = self.list(mailbox, pattern=pattern)[1]
        for mb in mbs:
            if mb is not None:
                mailboxName = re.search('\(.*\) ".*" "(.*)"', mb.decode()).groups()[0]
                mailboxes.append(mailboxName)
        return mailboxes


    def update(self, mailbox='INBOX.' + config.mailbox):

        logging.info("Updating mailbox: " + mailbox)

        # Did we receive any new command message in the INBOX or in the given mailbox ?
        mailboxes = ['INBOX', mailbox]
        # Or are there older command messages already stored under their own folders ?
        mailboxes += self.listMailboxes(mailbox)

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
            # Create a mailbox for that feed
            feed = YFeed(url)
            logging.info("This feed has this title: " + feed.title())

            commandPaths = [mbx for (mbx, uid) in feeds[url]]
            path = feed.path(commandPaths = commandPaths, agent = self, mailbox = mailbox) 
            # Move corresponding command messages from INBOX to that new folder
            for mb, uid in feeds[url]:
                if mb[0] != '"':
                    mb = '"' + mb + '"'
                self.moveUID(uid, fromMailbox=mb, toMailbox=path)
                self.select(mailbox=mb)
                self.expunge()
            feed.updateEntries(agent = self, mailbox = mailbox)

        return 'OK'


    def loadOPML(self, filename = None, mailbox = 'INBOX.' + config.mailbox):

        if filename is None:
            return
        f = open(filename, 'rt')
        tree = ElementTree.parse(f)
        root = tree.getroot()

        def createMailboxes(root, rootMailbox):
            for child in root.getchildren():
                childMailbox = rootMailbox
                if child.tag == 'outline':
                    url = child.get('xmlUrl')
                    title = child.get('title')
                    feed = YFeed(url)
                    if title is not None:
                        feed.title(title)
                    childMailbox = feed.createMailbox(agent = self, parentMailbox = rootMailbox)
                createMailboxes(child, childMailbox)
        
        createMailboxes(root, mailbox)


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
