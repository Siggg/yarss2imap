import imaplib
import config

class Yarss2imapAgent(imaplib.IMAP4):
    def __init__(self):
        imaplib.IMAP4.__init__(self,config.servername,config.port)
    def login(self):
        status, message = imaplib.IMAP4.login(self, config.username, config.password)
        return status
    def select(self, mailbox='INBOX.yarss2imap'):
        status, message = imaplib.IMAP4.select(self, mailbox)
        if status == 'NO': # there's not yarss2imap mailbox yet, let's create one
           imaplib.IMAP4.select(self)
           imaplib.IMAP4.create(self, mailbox) 
           imaplib.IMAP4.subscribe(self, mailbox)
           status, message = imaplib.IMAP4.select(self, mailbox)
        return status 
    def close(self):
        status, message = imaplib.IMAP4.close(self)
        return status
    def logout(self):
        status, message = imaplib.IMAP4.logout(self)
        return status    


if __name__ == "__main__":
    import doctest
    doctest.testfile("README.md")
