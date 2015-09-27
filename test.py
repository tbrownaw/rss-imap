import config
from imapwrapper import IMAPError, ImapWrapper

from email.mime.text import MIMEText
from html.parser import HTMLParser
import email.utils as utils
from time import strftime

import feedparser
import yaml





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

def read_email_config(wrap):
    for msg in wrap.fetch_messages('.config', 'SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
        if msg.is_multipart:
            for part in filter(lambda p: 'Folders' in p.get_param('Name', '(none)'), msg.get_payload()):
                ss = part.get_payload(None, True).decode('UTF-8')
                for fc in feed_configs_from_string(ss):
                    yield fc
        else:
            for fc in feed_configs_from_string(msg.get_payload()):
                yield fc


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

def item_message_id(item):
    return item.get('id', item.link).replace(' ', '_')

def rss_item_to_email(item):
    try:
        text = '<p>Item Link: <a href="%s">%s</a></p><br>%s' % (item.link, item.link, item.summary)
        email = MIMEText(text, "html")
        email['Subject'] = strip_html(item.title)
        email['From'] = item.get('author', '(Author Not Provided)')
        email['Message-Id'] = item_message_id(item)
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


def run_once():
    W = ImapWrapper(config.hostname, config.username, config.password)

    W.ensure_folder('.config')
    W.ensure_folder('RSS/')

    feeds = list(read_email_config(W))

    for feed in feeds:
        content = feedparser.parse(feed.URL)
        if content.bozo:
            print(" --> Feed %s had bozo set for '%s'" % (feed.Folder, content.bozo_exception))
        W.create_subscribe_folder('RSS/' + feed.Folder)
        def emails_to_add():
            for item in content.entries:
                if not W.have_message_with_id('RSS/' + feed.Folder, item_message_id(item)):
                    yield rss_item_to_email(item)
        for email in emails_to_add():
            if email['Subject'] == '':
                raise Error('Blank Subject')
            if email['Date'] == '':
                raise Error('Blank Date')
            typ, detail = W.append(feed.quoted_folder(), '', '', str(email).encode('utf-8'))
            if typ != "OK":
                raise IMAPError('Could not add item: %s' % detail)
            print('Feed "%s", new item "%s"' % (feed.Folder, email['Subject']))

    W.logout()

run_once()
