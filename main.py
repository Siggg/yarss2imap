import imaplib
import config
import email, email.message, email.header, email.utils
import email.mime.multipart, email.mime.text
import re
import feedparser
import urllib.parse
import time, datetime
import sys
import html2text
import unicodedata
import logging
logging.basicConfig(
        filename=config.logfile,
        format='%(levelname)s:%(asctime)s %(message)s',
        level=logging.DEBUG)
from xml.etree import ElementTree



def imapify(string):
    """ Return a version of the given string which
    can be used as a mailbox name by an IMAP server. """

    result = unicodedata.normalize('NFKD', string)
    result = result.encode('ASCII', 'ignore')
    result = result.decode()
    result = result.replace("/", "?")
    result = result.replace(".", "-")
    result = result.replace('"', "-")
    return result



class YFeed(object):
    """ This is a yarss2imap RSS feed mapped to an IMAP mailbox. """

    def __init__(self, url=None):

        # URL of the feed
        self.url = url

        # Parsed feed
        self.feed = None
        if url is not None:
            self.feed = feedparser.parse(url)

        # Title of the feed
        self._title = None

        # Safe title to be used as the name of a mailbox
        self._safeTitle = None

        # Path of the mailbox where this feed is represented
        self._mailbox = None


    def title(self, title=None):
        """ Returns the title of the feed. """

        if title is not None:
            self._title = title
        if self._title is not None:
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

        if self._safeTitle is not None:
            return self._safeTitle
        self._safeTitle = imapify(self.title())
        return self._safeTitle


    def mailbox(self,
                agent=None,
                targetMailbox='INBOX.' + config.mailbox):
        """ Returns the mailbox associated with this feed. """

        if self._mailbox is not None:
            return self._mailbox
        if agent is None:
            return None

        # Create one
        self._mailbox = targetMailbox
        logging.info("Creating mailbox: " + self._mailbox)
        status, message = agent.create(self._mailbox)
        if status != 'OK':
            # it probably already exists
            logging.info("Could not create mailbox: " + self._mailbox)
            logging.info("    error message was: " + str(message))
        status, message = agent.subscribe(self._mailbox)
        if status != 'OK':
            logging.error("Could not subscribe to mailbox: " + self._mailbox)
            logging.error("    error message was: " + str(message))
        return self._mailbox


    def createMessage(self, entry=None):
        """ Creates a message representing a given feed entry. """

        logging.info("Creating message about: " + entry.title)
        msg = email.mime.multipart.MIMEMultipart('alternative')
        msg.set_charset(self.feed.encoding)
        author = self.title()
        try:
            author = entry.author + " @ " + author
        except AttributeError:
            pass
        msg['From'] = author
        msg['Subject'] = entry.title
        msg['To'] = config.username
        try:
            msg['Date'] = email.utils.format_datetime(
                    datetime.datetime.fromtimestamp(
                        time.mktime(
                            entry.updated_parsed)))
        except AttributeError:
            try:
                msg['Date'] = email.utils.format_datetime(
                        datetime.datetime.fromtimestamp(
                            time.mktime(
                                entry.published_parsed)))
            except AttributeError:
                pass
        headerName = 'X-Entry-Link'
        entryLinkHeader = email.header.Header(s=entry.link,
                                              charset=self.feed.encoding)
        msg[headerName] = entryLinkHeader
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

        from io import BytesIO
        from email.generator import BytesGenerator
        bytesIO = BytesIO()
        bytesGenerator = BytesGenerator(bytesIO,
                                        mangle_from_=True,
                                        maxheaderlen=60)
        bytesGenerator.flatten(msg)
        text = bytesIO.getvalue()

        return text


    def updateEntries(self, agent=None):
        """ Guarantees that there is one message in the given mailbox
        for each entry in the feed. """

        if agent is None:
            return

        mailbox = self.mailbox(agent=agent)

        # Create one message per feed item
        nbOfEntries = str(len(self.feed.entries))
        logging.info("Examining " + nbOfEntries + " feed entries.")
        agent.select(mailbox=mailbox)
        for entry in self.feed.entries:

            # Is there already a message for this entry ?
            headerName = 'X-Entry-Link'
            try:
                agent.literal = entry.link.encode(self.feed.encoding)
                # ^-- this is an undocumented imaplib feature
                status, data = agent.uid(
                    'search',
                    'CHARSET',
                    self.feed.encoding,
                    'UNDELETED HEADER ' + headerName)
            except:
                logging.error('Could not search for entry link: ' + entry.link)
            if status == 'OK' and data[0] not in [None, b'']:
                # There is already one, move on !
                continue
            elif status != 'OK':
                logging.error('Could not search for entry URL: ' + entry.link)

            msg = self.createMessage(entry=entry)
            status, error = agent.append(mailbox,
                                         '',
                                         imaplib.Time2Internaldate(time.time()),
                                         msg)
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
            + "' from this URL: " + str(self.url))
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
            logging.error('Could not append message: ' + str(error))
        else:
            logging.info('Created feed message in mailbox: ' + path)
        return path



class YCommandMessage(object):
    """ A yarss2imap command represented as a message. """

    def __init__(self, message=None, mailbox=None, messageUID=None, agent=None):

        self.message = message
        self.mailbox = mailbox
        if mailbox is not None:
            if self.mailbox[0] != '"':
                self.mailbox = '"' + self.mailbox + '"'
        self.messageUID = messageUID
        self.agent = agent


    def remove(self):
        """ Deletes the command message. """

        if self.mailbox is None or self.messageUID is None:
            return 'OK'

        # Remove OPML command messages
        self.agent.select(self.mailbox)
        status, msg = self.agent.uid('store',
                                     self.messageUID,
                                     '+FLAGS',
                                     '\\Deleted')
        if status != 'OK':
            logging.error("Could not delete message with UID: " + \
                          self.messageUID + \
                          " in mailbox: " + \
                          self.mailbox)
            logging.error("Error message was: " + msg)
        return status


class YOPMLCommandMessage(YCommandMessage):
    """ An OPML document is to be loaded as a hierarchy of
    mailboxes including feed commands. Is represented as a
    message with 'OPML' as its subject and having an OPML
    document attached or as the main body.

    When executed, a hierarchy of mailboxes will
    be created according to the hierarchy of outlines described
    in the OPML files. outlines with an xmlUrl attribute will
    be created as mailboxes with a "feed <xmlUrl>"-titled
    message within.
    """

    def __init__(self, message=None, mailbox=None, messageUID=None, agent=None):

        YCommandMessage.__init__(self,
                                 message=message,
                                 mailbox=mailbox,
                                 messageUID=messageUID,
                                 agent=agent)
        opmlMimeTypes = ['text/xml', 'text/x-opml+xml']
        self.opml = None
        if message is None:
            return
        if message.get_content_maintype() == 'multipart':
            parts = message.get_payload()
            for part in parts:
                if part.get_content_type() in opmlMimeTypes:
                    self.opml = part.get_payload(decode=True)
                elif message.get_content_type() in opmlMimeTypes:
                    self.opml = message.get_payload(decode=True)


    def execute(self, underMailbox='INBOX' + config.mailbox):
        """ Execute the OPML command using given agent:
            - create the hierarchy of outlines as mailboxes
            with feeds,
            - remove the message. """

        if self.agent is None:
            logging.error("Could not execute without any agent.")
            return
        if self.opml is None:
            logging.error("Could not load OPML when OPML is None.")
            return

        # Create mailboxes for OPML content
        logging.info("Importing 1 OPML file.")
        root = ElementTree.fromstring(self.opml)

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
                    childMailbox = feed.createMailbox(agent=self.agent,
                                                      parentMailbox=rootMailbox)
                createMailboxes(child, childMailbox)

        createMailboxes(root, underMailbox)
        return self.remove()


class YFeedCommandMessage(YCommandMessage):
    """ A feed is to be updated. This command is represented
    as a message with "feed <feedURL>" as its subject line :

        feed http://...

    """

    def __init__(self, message=None, mailbox=None, messageUID=None, agent=None):

        YCommandMessage.__init__(self,
                                 message=message,
                                 mailbox=mailbox,
                                 messageUID=messageUID,
                                 agent=agent)
        subject = message['Subject']
        self.feedURL = re.search(r'feed\s+(.*)', subject).groups()[0]

    def execute(self, underMailbox='INBOX' + config.mailbox):
        """ Executes the feed command using agent :
            - move the feed message to a dedicated feed mailbox
            if needed
            - update this mailbox according to feed entries. """

        logging.info("Updating feed from URL: " + self.feedURL)
        # Create a mailbox for that feed
        feed = YFeed(self.feedURL)
        logging.info("This feed has this title: " + feed.title())

        # If needed, move that feed message to the feed mailbox
        if self.mailbox in ['INBOX', '"INBOX"']:
            # This feed needs its own mailbox.
            newMailbox = '"' + \
                         underMailbox.strip('"') + \
                         '.' + \
                         feed.safeTitle() + \
                         '"'
            feedMailbox = feed.mailbox(agent=self.agent,
                                       targetMailbox=newMailbox)
        else:
            # This feed will be in same mailbox as its
            # command message.
            feedMailbox = feed.mailbox(agent=self.agent,
                                       targetMailbox=self.mailbox)
        if self.mailbox != feedMailbox:
            # The feed command message must go into
            # the feed mailbox.
            self.agent.moveUID(self.messageUID,
                               fromMailbox=self.mailbox,
                               toMailbox=feedMailbox)
            self.agent.select(mailbox=feedMailbox)
            self.mailbox = feedMailbox

        # Now update entries in that mailbox
        feed.updateEntries(agent=self.agent)
        return 'OK'



class Yarss2imapAgent(imaplib.IMAP4):       #pylint: disable-msg=R0904
    """ An IMAP4 agent that can manage RSS feeds as mailboxes. """

    def __init__(self):

        logging.info("-----------------------------------------------")
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
        mbox = mailbox
        if mbox[0] != '"':
            mbox = '"' + mbox + '"'
        status, message = self.IMAP.select(self, mbox)
        if status == 'NO': # there's no such mailbox, let's create one
            self.IMAP.select(self)
            status, message = self.IMAP.create(self, mbox)
            if status != "OK":
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
            logging.error("   error message was: " + str(msg))
        status, msg = self.uid('store', uid, '+FLAGS', '\\Deleted')
        if status != 'OK':
            logging.error("Could not delete message with UID: " + uid)
            logging.error("   error message was: " + str(msg))


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


    def listCommands(self, mailbox='INBOX' + config.mailbox):
        """ Returns a list of command messages found in the given mailbox. """

        logging.info("Looking for command messages in: " + mailbox)
        self.select(mailbox)
        self.recent()
        commandMessages = []

        commandPattern = {
                'feed': 'HEADER Subject "feed "',
                'OPML': 'HEADER Subject "OPML"'
                }

        for command, pattern in commandPattern.items():

            status, data = self.uid('search', None, 'UNDELETED ' + pattern)
            messageUIDs = data[0].decode().split()
            logging.info("Found " + \
                         str(len(messageUIDs)) + \
                         " command messages of type '" + \
                         command + \
                         "' in mailbox: " + \
                         mailbox)

            for uid in messageUIDs:
                msgBin = self.uid('fetch', uid, '(RFC822)')[1][0][1]
                msg = email.message_from_bytes(msgBin)
                if command == "feed":
                    commandMessage = YFeedCommandMessage(message=msg,
                                                         mailbox=mailbox,
                                                         messageUID=uid,
                                                         agent=self)
                elif command == "OPML":
                    commandMessage = YOPMLCommandMessage(message=msg,
                                                         mailbox=mailbox,
                                                         messageUID=uid,
                                                         agent=self)
                commandMessages.append(commandMessage)

        return commandMessages


    def update(self, mailbox='INBOX.' + config.mailbox):
        """ Looks for command messages in the INBOX and under the given
        mailbox. Then executes these commands. Commands are given
        in the subject line of messages. Arguments can be given in the
        subject line or can be attachments.
        """

        logging.info("Updating mailbox: " + mailbox)

        # Did we receive any new command message in the INBOX
        # or in the given mailbox ?
        listedMailboxes = ['INBOX', mailbox]
        # Or are there older command messages already stored under
        # their own folders ?
        listedMailboxes += self.listMailboxes(mailbox)

        # Search for such messages and their command line in those mailboxes
        commands = []
        for listedMailbox in listedMailboxes:
            commands += self.listCommands(listedMailbox)

        logging.info("Found " + \
                     str(len(commands)) + \
                     " command messages under mailbox: " + \
                     mailbox)

        # Remove duplicate command messages
        opmls = {}
        feedCommandsByURL = {}
        uniqueCommands = commands.copy()
        for command in commands:
            if isinstance(command, YOPMLCommandMessage):
                if command.opml in opmls.keys():
                    # We already know this OPML.
                    # Let's remove that command.
                    command.remove()
                    uniqueCommands.remove(command)
                else:
                    opmls[command.opml] = True
            elif isinstance(command, YFeedCommandMessage):
                if command.feedURL in feedCommandsByURL.keys():
                    # We already have this feed in another command
                    otherCommand = feedCommandsByURL[command.feedURL]
                    if len(command.mailbox) > len(otherCommand.mailbox):
                        # This command path is longer than the longest so far
                        # for that URL.
                        # It's the only one we want to keep.
                        feedCommandsByURL[command.feedURL] = command
                        otherCommand.remove()
                        uniqueCommands.remove(otherCommand)
                    else:
                        # This command is redundant. Let's remove it.
                        command.remove()
                        uniqueCommands.remove(command)
                else:
                    # This is the first feed command message for this URL
                    feedCommandsByURL[command.feedURL] = command

        logging.info("Found " + \
                     str(len(uniqueCommands)) + \
                     " unique commands under mailbox: " + \
                     mailbox)
        for command in uniqueCommands:
            result = command.execute(underMailbox=mailbox)
            if result is None:
                logging.error('Could not execute command: ' + str(command))
                break

        return result


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
