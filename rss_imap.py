import config

import datetime
from email.mime.text import MIMEText
from html.parser import HTMLParser
import email.utils as utils
import re
import sys
from time import strftime
import socket

import feedparser
import yaml

from imap_wrapper import ImapWrapper

import pprint


class FilterError(IOError):
    pass


def item_message_id(feed, item):
    msgid = item.get('id', item.link)
    if not msgid:
        msgid = feed.Name + " / " + item.title + " AT " + item.get('date', 'No date')
    msgid = msgid.replace(' ', '_')
    msgid = re.sub('[^\x00-\x7f]', '_', msgid)
    return msgid

def rss_item_to_email(item, feed):
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
        text = '<p>Item Link: <a href="%s">%s</a></p>' % (item.link, item.link)
        if 'summary' in item:
            text = text + "<br>" + item.summary
        email = MIMEText(text, "html")
        email['Subject'] = config.subject_template.format(name=feed.Name, subject=strip_html(item.title))
        email['From'] = item.get('author', '(Author Not Provided)')
        email['Message-Id'] = item_message_id(feed, item)
        if 'published' in item:
            date = item.published
            date_parts = item.published_parsed
        elif 'updated' in item:
            date = item.updated
            date_parts = item.updated_parsed
        elif 'created' in item:
            date = item.created
            date_parts = item.created_parsed
        else:
            date = None
            date_parts = datetime.datetime.now().timetuple()
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
        self.email = rss_item_to_email(rss_item, feed)
        self.message_id = self.email['Message-Id']


class FeedConfig:
    def __init__(self, dat):
        self.Name = dat['Name']
        self.URL = dat['URL']
    def __repr__(self):
        return ("{ Folder: %s; URL: %s }" % (self.Name, self.URL))
    def quoted_folder(self):
        return config.feed_folder_template.format(name=self.Name)



class RssIMAP:
    def __init__(self):
        pass

    def connect_imap(self, hostname, username, password):
        self._W = ImapWrapper(hostname, username, password)
        self._W.ensure_folder('.config')

    def parse_configs(self, configs):
        feed_configs = []
        app_config = None
        for dat in configs:
            #pprint.pprint(dat)
            for item in filter(lambda p: p != None, yaml.safe_load_all(dat)):
                if 'Configuration' in item:
                    #pprint.pprint(item)
                    app_config = item['Configuration']
                else:
                    feed_configs.append(FeedConfig(item))
        # Figure out a better place to put this...
        def approx_item(dict, key):
            #print("Looking for key '" + key + "' in:")
            #pprint.pprint(dict.keys())
            m = list(filter(lambda k: re.search('( |^)' + key + '$', k), dict.keys()))
            if m:
                #print("*** " + m[0] + " = " + dict[m[0]])
                return dict[m[0]]
            return None
        if app_config:
            #print("*** Reading app config...")
            config.feed_folder_template = approx_item(app_config, 'FolderTemplate') or config.feed_folder_template #app_config['FolderTemplate']
            config.subject_template = approx_item(app_config, 'SubjectTemplate') or config.subject_template #app_config['SubjectTemplate']
        #pprint.pprint(feed_configs)
        return feed_configs

    def config_data_from_imap(self):
        # Don't be lazy about this.
        ret = []
        for msg in self._W.fetch_messages('.config', 'SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
            if msg.is_multipart():
                #pprint.pprint(msg.get_content_type())
                for part in msg.get_payload():
                    #pprint.pprint(part.items())
                    name = part.get_param('Name', '(none)')
                    if 'Folders' in name:
                        ret.append(part.get_payload(None, True).decode('UTF-8'))
                    elif name == '(none)' and part.get_content_type() == 'text/plain':
                        ret.append(part.get_payload(None, True).decode('UTF-8'))
            else:
                ret.append(msg.get_payload())
        return ret

    def get_feed_config_from_imap(self):
        the_data = self.config_data_from_imap()
        return self.parse_configs(the_data)

    def fetch_feed_items(self, feed):
        sys.stdout.write("Fetching feed %s\n" % (feed.URL))
        content = feedparser.parse(feed.URL)
        sys.stdout.write("Done fetching feed %s\n" % (feed.URL))
        if content.bozo:
            sys.stderr.write(" --> Feed %s had bozo set for '%s'\n" % (feed.Name, content.bozo_exception))
        for item in content.entries:
            yield FeedItem(feed, item)

    def fetch_all_feed_items(self):
        for feed in self.get_feed_config_from_imap():
            for item in self.fetch_feed_items(feed):
                yield item

    def filter_items(self, items):
        for item in items:
            self._W.create_subscribe_folder(item.feed.quoted_folder())
            try:
                if not self._W.have_message_with_id(item.feed.quoted_folder(), item.message_id):
                    yield item
            except:
                raise FilterError("Could not check for presence of item with subject %s from feed %s" % (item.email['Subject'], item.feed.Name))

    def save_items_to_imap(self, items):
        for item in items:
            sys.stdout.write('New item "%s" for feed "%s", with message_id "%s"\n' % (item.email['Subject'], item.feed.Name, item.message_id))
            self._W.append(item.feed.quoted_folder(), item.email)

    def disconnect(self):
        self._W.logout()


if __name__ == '__main__':
    socket.setdefaulttimeout(10)
    x = RssIMAP()
    x.connect_imap(config.hostname, config.username, config.password)
    x.save_items_to_imap(x.filter_items(x.fetch_all_feed_items()))
    x.disconnect()
