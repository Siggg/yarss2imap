import imaplib
import config

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
    def select(self, mailbox='INBOX.yarss2imap'):
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


if __name__ == "__main__":
    import doctest
    doctest.testfile("README.md")
