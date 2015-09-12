import config

import email
from email.mime.text import MIMEText
from html.parser import HTMLParser
import email.utils as utils
import imaplib
import re
from time import strftime

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
                raise Error("Could not extract folder name from %s" % ent)
    typ, listing = M.list()
    return extract_names(listing)


def search(*args):
    try:
        typ, listing = M.search(None, *args)
    except:
        print("Invalid search args: ", args)
        raise
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

class FeedConfig:
    def __init__(self, dat):
        self.Folder = dat['Folder Name']
        self.URL = dat['Feed URL']
    def __repr__(self):
        return ("{ Folder: %s; URL: %s }" % (self.Folder, self.URL))
    def quoted_folder(self):
        return '"RSS/%s"' % self.Folder
    def create_folder(self):
        print('Creating folder for %s' % self.Folder)
        M.create(self.quoted_folder())
        M.subscribe(self.quoted_folder())
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

# Ensure folders exist
for feed in feeds:
    if not any(f == 'RSS/' + feed.Folder for f in names):
        feed.create_folder()

# Cribbing things from StackOverflow is fun. :)
def strip_html(dat):
    class TagStripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.convert_charrefs = True
            self.texts = []
        def handle_data(self, t):
            self.texts.append(t)
        def result(self):
            return ''.join(self.texts)
    ts = TagStripper()
    ts.feed(dat)
    ts.close()
    return ts.result()

def rss_item_to_email(item):
    try:
        text = '<p>Item Link: <a href="%s">%s</a></p><br>%s' % (item.link, item.link, item.summary)
        email = MIMEText(text, "html")
        email['Subject'] = strip_html(item.title)
        email['From'] = item.get('author', '(Author Not Provided)')
        email['Message-Id'] = item.get('id', item.link).replace(' ', '_')
        if 'published' in item:
            date = item.published
            date_parts = item.published_parsed
        elif 'updated' in item:
            date = item.updated
            date_parts = item.updated_parsed
        elif 'created' in item:
            date = item.created
            date_parts = item.created_parsed
        if date_parts is None:
            date_parts = utils.parsedate(strip_html(date))
        # RSS feeds may contain parsable dates that aren't allowed in email.
        if not (date_parts is None):
            date = strftime("%A, %b %d %Y %H:%M:%S %Z", date_parts)
        email['Date'] = strip_html(date)
        return email
    except:
        print("***ERROR while processing this item:\n", item)
        raise

for feed in feeds:
    content = feedparser.parse(feed.URL)
    #print(content.channel)
    feed.select_folder()
    def emails_to_add():
        for item in content.entries:
            email = rss_item_to_email(item)
            existing = search('HEADER', 'Message-Id', email['Message-Id'])
            if not any(existing):
                yield email
    for email in emails_to_add():
        if email['Subject'] == '':
            raise Error('Blank Subject')
        if email['Date'] == '':
            raise Error('Blank Date')
        typ, detail = M.append(feed.quoted_folder(), '', '', str(email).encode('utf-8'))
        print('Append result for "%s": %s %s' % (email['Subject'], typ, detail))

M.logout()
