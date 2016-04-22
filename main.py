import imaplib
import config
import email, email.message, email.mime.multipart, email.mime.text, email.header
import re
import feedparser
import urllib.parse
import time
import sys
import html2text
import unicodedata
import logging
logging.basicConfig(
        filename=config.logfile,
        format='%(levelname)s:%(asctime)s %(message)s',
        level=logging.DEBUG)
from xml.etree import ElementTree


class YFeed(object):
    """ This is a yarss2imap RSS feed mapped to an IMAP mailbox. """

    def __init__(self, url=None):
        self.url = url
        self.feed = None
        if url is not None:
            self.feed = feedparser.parse(url)
        self._title = None
        self._safeTitle = None
        self._path = None


    def title(self, title=None):
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
        """ Returns a version of the feed title that can safely be used
        as the name of an IMAP mailbox. """

        if hasattr(self, '_safeTitle'):
            return self._safeTitle
        self._safeTitle = unicodedata.normalize('NFKD', self.title())
        self._safeTitle = self._safeTitle.encode('ASCII', 'ignore')
        self._safeTitle = self._safeTitle.decode()
        self._safeTitle = self._safeTitle.replace("/", "?").replace(".", "-")
        return self._safeTitle


    def path(self,
             commandPaths=None,
             agent=None,
             mailbox='INBOX.' + config.mailbox):
        """ Returns the path of the mailbox associated with this feed. """

        if hasattr(self, '_path'):
            return self._path
        if agent is None:
            return None
        if commandPaths == None:
            commandPaths = []

        # Several mailboxes may contain a "feed" command with the URL of this
        # feed.
        # The one with the longest path is the one to be associated with this
        # feed.
        # Unless it is the main mailbox, then we are to look for one based on
        # a matching name.
        longestPath = mailbox
        for path in commandPaths:
            if len(path) > len(longestPath):
                longestPath = path
        self._path = longestPath
        if self._path != mailbox:
            if self._path[0] != '"':
                self._path = '"' + self._path + '"'
            return self._path

        # OK. So. No matching mailbox with a "feed" command for the URL of this
        # feed.
        # Does this feed have a mailbox with a name matching its title ?
        paths = agent.listMailboxes(mailbox,
                                    pattern='"*' + self.safeTitle() + '"')
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


    def createMessage(self, entry=None):
        """ Creates a message representing a given feed entry. """

        logging.info("Creating message about: " + entry.title)
        msg = email.mime.multipart.MIMEMultipart('alternative')
        msg.set_charset(self.feed.encoding)
        try:
            msg['From'] = entry.author + " / " + self.title()
        except AttributeError:
            msg['From'] = self.title()
            msg['Subject'] = entry.title
            msg['To'] = config.username
        try:
            msg['Date'] = entry.published
        except AttributeError:
            pass
        entryLinkHeader = email.header.Header(entry.link, 'utf-8')
        msg['X-Entry-Link'] = entryLinkHeader
        try:
            content = entry.content[0]['value']
        except AttributeError:
            try:
                content = entry.summary
            except AttributeError:
                content = entry.description
        html = content
        text = html2text.html2text(html)
        text = 'Retrieved from ' + entry.link + '\n' + text
        html = html + \
               '<p><a href="' + \
               entry.link + \
               '">Retrieved from ' + \
               entry.link + \
               '</a></p>'
        part1 = email.mime.text.MIMEText(text, 'plain')
        part2 = email.mime.text.MIMEText(html, 'html')
        msg.attach(part1)
        msg.attach(part2)

        return msg


    def updateEntries(self, agent=None, mailbox='INBOX.' + config.mailbox):
        """ Guarantees that there is one message in the given mailbox
        for each entry in the feed. """

        if agent is None:
            return

        path = self.path(agent=agent, mailbox=mailbox)

        # Create one message per feed item
        nbOfEntries = str(len(self.feed.entries))
        logging.info("Examining " + nbOfEntries + " feed entries.")
        agent.select(mailbox=path)
        for entry in self.feed.entries:

            # Is there already a message for this entry ?
            try:
                entryLinkHeader = email.header.Header(entry.link, 'utf-8')
                entryLinkHeader = entryLinkHeader.encode()
                status, data = agent.uid(
                    'search',
                    None,
                    'HEADER X-Entry-Link "' + entryLinkHeader + '"')
            except:
                import pdb; pdb.set_trace()
                logging.error('Could not search for entry link: ' + entry.link)
            if data[0] not in [None, b'']:
                # There is already one, move on !
                continue

            msg = self.createMessage(entry=entry)
            status, error = agent.append(path,
                                         '',
                                         imaplib.Time2Internaldate(time.time()),
                                         msg.as_bytes())
            if status != 'OK':
                logging.error('Could not append message: ' + error)


    def createMailbox(self,
                      agent=None,
                      parentMailbox='INBOX.' + config.mailbox):
        """ Creates a mailbox with a given name and a command
            message for a feed at the given URL.
            If no name but a URL is given, the name is the title of
            feed at this URL.
            If no URL but a name is given, the mailbox is created
            without any command message."""

        logging.info("Creating a feed mailbox named '" + self.title() \
            + "' and this URL: " + str(self.url))
        if self.url is None and self.title() is None:
            logging.error('Could not create mailbox without a feed nor a name.')
        if agent is None:
            logging.error('Could not create mailbox without '
                          'an IMAP agent: ' + str(self.url))
        path = '"' + parentMailbox.strip('"') + '.' + self.safeTitle() + '"'
        agent.select(mailbox=path)
        if self.url is None:
            return path
        msg = email.mime.text.MIMEText("", "plain")
        msg['Subject'] = "feed " + str(self.url)
        msg['From'] = config.authorizedSender
        msg['To'] = config.authorizedSender
        status, error = agent.append(path,
                                     '',
                                     imaplib.Time2Internaldate(time.time()),
                                     msg.as_bytes())
        if status != 'OK':
            logging.error('Could not append message: ' + error)
        else:
            logging.info('Created feed message in mailbox: ' + path)
        return path



class Yarss2imapAgent(imaplib.IMAP4):       #pylint: disable-msg=R0904
    """ An IMAP4 agent that can manage RSS feeds as mailboxes. """

    def __init__(self):

        logging.info("Initializing new agent.")
        try:
            imaplib.IMAP4_SSL.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4_SSL
        except:
            imaplib.IMAP4.__init__(self, config.servername, config.port)
            self.IMAP = imaplib.IMAP4


    def login(self):
        """ Logs in using credentials given in config file. """

        logging.info("Logging in.")
        status, message = self.IMAP.login(self,
                                          config.username,
                                          config.password)
        return status


    def select(self, mailbox='INBOX.' + config.mailbox):
        """ Selects given mailbox or mailbox given in config gile. """

        logging.info("Selecting mailbox: " + mailbox)
        mbox = unicodedata.normalize('NFKD', mailbox).encode('ASCII', 'ignore')
        if mailbox[0] != '"':
            mbox = '"' + mailbox + '"'
        status, message = self.IMAP.select(self, mbox)
        if status == 'NO': # there's no such mailbox, let's create one
            self.IMAP.select(self)
            status, message = self.IMAP.create(self, mbox)
            if status != "OK":
                import pdb; pdb.set_trace()
                logging.error("Could not create mailbox: " + str(mbox))
            self.IMAP.subscribe(self, mbox)
            status, message = self.IMAP.select(self, mbox)
            if status != "OK":
                logging.error("Could not select mailbox: " + str(mbox))
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
        lines = self.list(mailbox)[1]
        self.select(mailbox='INBOX')
        for line in lines:
            if line is None:
                continue
            line = line.decode()
            path = re.search(r'\(.*\) ".*" "(.*)"', line).groups()[0]
            if path[0] != '"':
                path = '"' + path + '"'
            status, message = self.unsubscribe(path)
            if status != 'OK':
                logging.error("Could not unsubscribe from: " + path)
            status, message = self.delete(path)
            if status != 'OK':
                logging.error("Could not delete path: " + path)
        self.unsubscribe(mailbox)
        return self.delete(mailbox)[0]


    def moveUID(self, uid, fromMailbox='INBOX', toMailbox='INBOX'):
        """ Moves message given by UID from one mailbox to another. """

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
        """ Lists mailbox paths under given mailbox and with names matching
        given pattern. """

        mailboxNames = []
        mailboxes = self.list(mailbox, pattern=pattern)[1]
        for mailboxFound in mailboxes:
            if mailboxFound is not None:
                mailboxName = re.search(r'\(.*\) ".*" "(.*)"',
                                        mailboxFound.decode()).groups()[0]
                mailboxNames.append(mailboxName)
        return mailboxNames


    def update(self, mailbox='INBOX.' + config.mailbox):
        """ Looks for command messages in the INBOX and under the given
        mailbox. Then executes these commands. Commands are given
        in the subject line of messages. Arguments can be given in the
        subject line or can be attachments.

        Only 2 commands are supported so far :

            feed http://...

            will update the feed with this URL. The corresponding
            mailbox will be created if it does not exist.

        and

            OPML

            will take an OPML file given as the body of or as an
            attachment to the message. A hierarchy of mailboxes will
            be created according to the hierarchy of outlines described
            in the OPML files. outlines with an xmlUrl attribute will
            be created as mailboxes with a "feed <xmlUrl>"-titled
            message within.

        """

        logging.info("Updating mailbox: " + mailbox)

        # Did we receive any new command message in the INBOX
        # or in the given mailbox ?
        listedMailboxes = ['INBOX', mailbox]
        # Or are there older command messages already stored under
        # their own folders ?
        listedMailboxes += self.listMailboxes(mailbox)

        # Search for such messages and their command line in those mailboxes
        feedCommands = {}
        opmlCommands = {}
        opmlPayloads = {}
        for listedMailbox in listedMailboxes:
            logging.info("Looking for command messages in: " + listedMailbox)
            self.select(listedMailbox)
            self.recent()

            # Search "feed http://...." command messages
            status, data = self.uid('search', None, 'HEADER Subject "feed "')
            feedMsgUIDs = data[0].decode().split()
            logging.info("Found " + \
                         str(len(feedMsgUIDs)) + \
                         " feed messages in mailbox: " + \
                         listedMailbox)
            for uid in feedMsgUIDs:
                msgBin = self.uid('fetch', uid, '(RFC822)')[1][0][1]
                msg = email.message_from_bytes(msgBin)
                feedCommands[(listedMailbox, uid)] = msg['Subject']

            # Search "OPML" command messages
            status, data = self.uid('search', None, 'HEADER Subject "OPML"')
            opmlMsgUIDs = data[0].decode().split()
            logging.info("Found " + \
                         str(len(opmlMsgUIDs)) + \
                         " OPML messages in mailbox: " + \
                         listedMailbox)
            opmlMimeTypes = ['text/xml', 'text/x-opml+xml']
            for uid in opmlMsgUIDs:
                msgBin = self.uid('fetch', uid, '(RFC822)')[1][0][1]
                msg = email.message_from_bytes(msgBin)
                if msg.get_content_maintype() == 'multipart':
                    parts = msg.get_payload()
                    for part in parts:
                        if part.get_content_type() in opmlMimeTypes:
                            opmlPayloads[part.get_payload(decode=True)] = True
                elif msg.get_content_type() in opmlMimeTypes:
                    opmlPayloads[msg.get_payload(decode=True)] = True
                opmlCommands[(listedMailbox, uid)] = True

        # Create mailboxes for OPML content
        logging.info("Importing " + \
                     str(len(opmlPayloads.keys())) + \
                     " OPML file(s).")
        for opml in opmlPayloads.keys():
            self.loadOPML(opml=opml, mailbox=mailbox)
        # Remove OPML command messages
        for mailbox, uid in opmlCommands.keys():
            self.select(mailbox)
            status, msg = self.uid('store', uid, '+FLAGS', '\\Deleted')
            if status != 'OK':
                logging.error("Could not delete message with UID: " + \
                              uid + \
                              " in mailbox: " + \
                              mailbox)
                logging.error("   error message was: " + msg)


        # Build the list of feed URL to be checked for new items
        feeds = {}
        for msgPath, feedCommand in feedCommands.items():
            try:
                feedURL = re.search(r'feed\s+(.*)', feedCommand).groups()[0]
            except AttributeError:
                logging.error('Could not parse this feed command: ' + \
                              str(feedCommand))

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
            path = feed.path(commandPaths=commandPaths,
                             agent=self,
                             mailbox=mailbox)
            # Move corresponding command messages from INBOX to that new folder
            for feedMailbox, uid in feeds[url]:
                if feedMailbox[0] != '"':
                    feedMailbox = '"' + feedMailbox + '"'
                self.moveUID(uid, fromMailbox=feedMailbox, toMailbox=path)
                self.select(mailbox=feedMailbox)
                self.expunge()
            feed.updateEntries(agent=self, mailbox=mailbox)

        return 'OK'


    def loadOPML(self, opml=None, mailbox='INBOX.' + config.mailbox):
        """ Creates mailboxes corresponding to the outlines
            of the given OPML string. """

        if opml is None:
            return
        root = ElementTree.fromstring(opml)

        def createMailboxes(root, rootMailbox):
            """ Creates a mailbox under the given rootMailbox
            for each child of the given root outline. """

            for child in root.getchildren():
                childMailbox = rootMailbox
                if child.tag == 'outline':
                    url = child.get('xmlUrl')
                    title = child.get('title')
                    feed = YFeed(url)
                    if title is not None:
                        feed.title(title)
                    childMailbox = feed.createMailbox(agent=self,
                                                      parentMailbox=rootMailbox)
                createMailboxes(child, childMailbox)

        createMailboxes(root, mailbox)


    def loop(self):
        """ Main loop. """

        logging.info("Agent starting loop.")
        try:
            while True:
                self.update()
                logging.info("Sleeping for 60 seconds.")
                time.sleep(60)
        except:
            logging.warning("Unexpected error:" + str(sys.exc_info()[0]))
            self.close()
            self.logout()
            raise
        logging.info("Agent stopping loop.")


if __name__ == "__main__":

    AGENT = Yarss2imapAgent()
    AGENT.login()
    AGENT.select()
    AGENT.loop()
    AGENT.close()
    AGENT.logout()
