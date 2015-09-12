import config

import email
from email.mime.text import MIMEText
import imaplib
import re

import feedparser
import yaml

M = imaplib.IMAP4_SSL(config.hostname)
M.login(config.username, config.password)



list_matcher = re.compile('^\(([^()]*)\) "([^"]*)" "([^"]*)"$')
def list_folders():
    def extract_names(ll):
        for ent in ll:
            m = list_matcher.match(ent.decode('US-ASCII'))
            if m:
                yield m.group(3)
            else:
                yield '!!!' + ("%s" % ent)
    typ, listing = M.list()
    #print(typ, listing)
    # There has got to be a better way to do this.
    for x in extract_names(listing):
        yield x

def search(*args):
    typ, listing = M.search(None, *args)
    for lst in listing:
        dd = lst.decode('US-ASCII')
        for m in dd.split(' '):
            if m:
                yield m


names = list(list_folders())

if not any(f == '.config' for f in names):
    print('Creating .config folder')
    M.create('.config')
if not any(f == 'RSS' for f in names):
    print('Creating toplevel RSS folder')
    M.create('RSS/')

#for nn in names:
#    print("Folder: " + nn)

class FeedConfig:
    def __init__(self, dat):
        self.Folder = dat['Folder Name']
        self.URL = dat['Feed URL']
    def __repr__(self):
        return ("{ Folder: %s; URL: %s }" % (self.Folder, self.URL))
    def quoted_folder(self):
        return '"RSS/%s"' % self.Folder
    def create_folder(self):
        print('Creating folder for %s' % Folder)
        M.create(self.quoted_folder())
    def select_folder(self):
        M.select(self.quoted_folder())

def feed_configs_from_string(dat):
    for item in yaml.load_all(dat):
        yield FeedConfig(item)

def read_email_config():
    M.select('.config')
    for num in search('SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
        typ, dat = M.fetch(num, '(RFC822)')
        msg_str = dat[0][1].decode('UTF-8')
        msg = email.message_from_string(msg_str)
        if msg.is_multipart:
            for part in filter(lambda p: 'Folders' in p.get_param('Name', '(none)'), msg.get_payload()):
                ss = part.get_payload(None, True).decode('UTF-8')
                for fc in feed_configs_from_string(ss):
                    yield fc
        else:
            for fc in feed_configs_from_string(msg.get_payload()):
                yield fc

feeds = list(read_email_config())
print(feeds)

# Ensure folders exist
for feed in feeds:
    if not any(f == 'RSS/' + feed.Folder for f in names):
        feed.create_folder()

def rss_item_to_email(item):
    try:
        text = item.link + "\r\n\r\n" + item.summary
        email = MIMEText(text, "html")
        email['Subject'] = item.title
        email['From'] = item.author
        email['Message-Id'] = item.get('id', item.link)
        email['Date'] = item.published if 'published' in item else item.updated if 'updated' in item else item.created
        return email
    except:
        print("***ERROR while processing this item:\n", item)
        raise

for feed in feeds:
    content = feedparser.parse(feed.URL)
    print(content.channel)
    print(len(content.entries))
    feed.select_folder()
    def emails_to_add():
        for item in content.entries:
            email = rss_item_to_email(item)
            existing = search('HEADER', 'Message-Id', email['Message-Id'])
            if not any(existing):
                yield email
    for email in emails_to_add():
        print("%s\n" % email)
        typ, detail = M.append(feed.quoted_folder(), '', '', str(email).encode('utf-8'))
        print("Append result: %s %s\n\n\n" % (typ, detail))

M.logout()
