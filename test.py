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

list_matcher = re.compile('^\(([^()]*)\) "([^"]*)" "([^"]*)"$')
class IMAPError(IOError):
    pass
class ImapWrapper:
    def __init__(self, host, user, pw):
        self.M = imaplib.IMAP4_SSL(host)
        self.M.login(user, pw)
        self._update_folders()
    def logout(self):
        self.M.logout()
    def _update_folders(self):
        def extract_names(ll):
            for ent in ll:
                m = list_matcher.match(ent.decode('US-ASCII'))
                if m:
                    yield m.group(3)
                else:
                    raise IMAPError("Could not extract folder name from %s" % ent)
        typ, listing = self.M.list()
        if typ != "OK":
            raise IMAPError("Failed to list folders: %s" % listing)
        self.folder_list = list(extract_names(listing))
    def ensure_folder(self, name):
        """Return True if the folder was created, False if it already existed."""
        search_name = name[:-1] if name.endswith('/') else name
        if not any(n == search_name for n in self.folder_list):
            typ, dtl = self.M.create('"' + name + '"')
            if typ != "OK":
                raise IMAPError("Could not create folder: %s" % dtl)
            self.folder_list.add(search_name)
            return True
        else:
            return False    
    # FIXME uses the context folder
    def search(self, *args):
        try:
            typ, listing = self.M.search(None, *args)
        except:
            raise IMAPError('Search failed with args "%s"' % str(args))
        for lst in listing:
            dd = lst.decode('US-ASCII')
            for m in dd.split(' '):
                if m:
                    yield m
    # FIXME uses the context folder
    def fetch(self, *args):
        return self.M.fetch(*args)
    def append(self, *args):
        return self.M.append(*args)
    def try_select_folder(self, name):
        typ, dtl = self.M.select('"' + name + '"')
        return typ == "OK"
    def select_create_folder(self, name):
        """Select the named folder, creating it if needed (and subscribing to it)."""
        created = self.ensure_folder(name)
        if created:
            typ, dtl = self.M.subscribe('"' + name + '"')
            if typ != "OK":
                raise IMAPError("Could not subscribe to folder %s" % name)
        if not self.try_select_folder(name):
            raise IMAPError("Could not select folder %s" % name)

W = ImapWrapper(config.hostname, config.username, config.password)

W.ensure_folder('.config')
W.ensure_folder('RSS/')



class FeedConfig:
    def __init__(self, dat):
        self.Folder = dat['Folder Name']
        self.URL = dat['Feed URL']
    def __repr__(self):
        return ("{ Folder: %s; URL: %s }" % (self.Folder, self.URL))
    def quoted_folder(self):
        return '"RSS/%s"' % self.Folder

def feed_configs_from_string(dat):
    for item in yaml.load_all(dat):
        yield FeedConfig(item)

def read_email_config():
    if not W.try_select_folder('.config'):
        raise Exception("No .config folder available on IMAP server.")
    for num in W.search('SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
        typ, dat = W.fetch(num, '(RFC822)')
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
    W.select_create_folder('RSS/' + feed.Folder)
    def emails_to_add():
        for item in content.entries:
            email = rss_item_to_email(item)
            existing = W.search('HEADER', 'Message-Id', email['Message-Id'])
            if not any(existing):
                yield email
    for email in emails_to_add():
        if email['Subject'] == '':
            raise Error('Blank Subject')
        if email['Date'] == '':
            raise Error('Blank Date')
        typ, detail = W.append(feed.quoted_folder(), '', '', str(email).encode('utf-8'))
        print('Append result for "%s": %s %s' % (email['Subject'], typ, detail))

W.logout()
