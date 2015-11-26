import config

import email
from email.mime.text import MIMEText
from html.parser import HTMLParser
import imaplib
import email.utils as utils
import re
import sys
from time import strftime

import feedparser
import yaml




class IMAPError(IOError):
    pass
class ImapWrapper:
    list_matcher = re.compile('^\(([^()]*)\) "([^"]*)" "([^"]*)"$')
    def __init__(self, host, user, pw):
        self.M = imaplib.IMAP4_SSL(host)
        self.M.login(user, pw)
        self._selected_folder = None
        self._update_folders()
    def logout(self):
        self.M.logout()
    def _update_folders(self):
        def extract_names(ll):
            for ent in ll:
                m = self.list_matcher.match(ent.decode('US-ASCII'))
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
            self.folder_list.append(search_name)
            return True
        else:
            return False    
    # FIXME uses the context folder
    def search(self, *args):
        try:
            typ, listing = self.M.search(None, *args)
        except:
            raise IMAPError('Search failed with args "%s"' % str(args))
        if typ != "OK":
            raise IMAPError('search() failed: %s' % listing)
        for lst in listing:
            dd = lst.decode('US-ASCII')
            for m in dd.split(' '):
                if m:
                    yield m
    
    def fetch_messages(self, folder, *search_args):
        ret = []
        self.select_folder(folder)
        for num in self.search(*search_args):
            typ, dat = self.M.fetch(num, '(RFC822)')
            if typ != "OK":
                raise IMAPError('Could not fetch searched message: %s' % dat)
            msg = email.message_from_string(dat[0][1].decode('UTF-8'))
            ret.append(msg)
        return ret

    def have_message_with_id(self, folder, msgid):
        self.select_folder(folder)
        res = list(self.search('HEADER', 'Message-Id', msgid, 'NOT', 'DELETED'))
        #sys.stderr.write('>>> Looking in folder "%s" for message-id "%s": got "%s"\n' % (folder, msgid, res))
        return any(res)
    
    def append(self, folder_name, email):
        typ, detail = self.M.append('"' + folder_name + '"', '', '', str(email).encode('utf-8'))
        if typ != 'OK':
            raise IMAPError('Could not add item: %s' % detail)
        
    # FIXME sets the context folder
    def select_folder(self, name):
        if self._selected_folder == name:
            return
        typ, dtl = self.M.select('"' + name + '"')
        if typ != "OK":
            raise IMAPError('Could not select folder "%s": %s' % (name, dtl))
        self._selected_folder = name
        
    def create_subscribe_folder(self, name):
        created = self.ensure_folder(name)
        if created:
            typ, dtl = self.M.subscribe('"' + name + '"')
            if typ != "OK":
                raise IMAPError("Could not subscribe to folder %s" % name)





class FeedConfig:
    def __init__(self, dat):
        self.Folder = dat['Folder Name']
        self.URL = dat['Feed URL']
    def __repr__(self):
        return ("{ Folder: %s; URL: %s }" % (self.Folder, self.URL))
    def quoted_folder(self):
        return '"RSS/%s"' % self.Folder




def item_message_id(item):
    return item.get('id', item.link).replace(' ', '_')

def rss_item_to_email(item):
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



class FeedItem:
    def __init__(self, feed, rss_item):
        self.feed = feed
        self.rss_item = rss_item
        self.email = rss_item_to_email(rss_item)
        self.message_id = self.email['Message-Id']



class RssIMAP:
    def __init__(self):
        pass
    
    def connect_imap(self, hostname, username, password):
        self._W = ImapWrapper(hostname, username, password)
        self._W.ensure_folder('.config')
        self._W.ensure_folder('RSS/')

    def parse_configs(self, configs):
        for dat in configs:
            for item in filter(lambda p: p != None, yaml.load_all(dat)):
                yield FeedConfig(item)

    def config_data_from_imap(self):
        # Don't be lazy about this.
        ret = []
        for msg in self._W.fetch_messages('.config', 'SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
            if msg.is_multipart():
                for part in filter(lambda p: 'Folders' in p.get_param('Name', '(none)'), msg.get_payload()):
                    ret.append(part.get_payload(None, True).decode('UTF-8'))
            else:
                ret.append(msg.get_payload())
        return ret
    
    def get_feed_config_from_imap(self):
        the_data = self.config_data_from_imap()
        return self.parse_configs(the_data)

    def fetch_feed_items(self, feed):
        content = feedparser.parse(feed.URL)
        if content.bozo:
            sys.stderr.write(" --> Feed %s had bozo set for '%s'\n" % (feed.Folder, content.bozo_exception))
        for item in content.entries:
            yield FeedItem(feed, item)

    def fetch_all_feed_items(self):
        for feed in self.get_feed_config_from_imap():
            for item in self.fetch_feed_items(feed):
                yield item

    def filter_items(self, items):
        for item in items:
            self._W.create_subscribe_folder('RSS/' + item.feed.Folder)
            if not self._W.have_message_with_id('RSS/' + item.feed.Folder, item.message_id):
                yield item

    def save_items_to_imap(self, items):
        for item in items:
            sys.stdout.write('New item "%s" for feed "%s"\n' % (item.email['Subject'], item.feed.Folder))
            self._W.append('RSS/' + item.feed.Folder, item.email)

    def disconnect(self):
        self._W.logout()


if __name__ == '__main__':
    x = RssIMAP()
    x.connect_imap(config.hostname, config.username, config.password)
    x.save_items_to_imap(x.filter_items(x.fetch_all_feed_items()))
    x.disconnect()