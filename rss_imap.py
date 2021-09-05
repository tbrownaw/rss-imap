import config

import datetime
from email.mime.text import MIMEText
from html.parser import HTMLParser
import email.utils as utils
import logging
import queue
import re
import sys
import threading
from time import strftime
import socket

import feedparser
import yaml

from imap_wrapper import ImapWrapper

class FilterError(IOError):
    pass

class TranslationException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        email['Subject'] = feed.format_subject(subject=strip_html(item.title))
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
    except Exception as e:
        raise TranslationException(item) from e


class FeedItem:
    def __init__(self, feed, rss_item):
        self.feed = feed
        self.rss_item = rss_item
        self.email = rss_item_to_email(rss_item, feed)
        self.message_id = self.email['Message-Id']


class FeedConfig:
    def __init__(self, dat, *parent_configs):
        def _extract_setting(name):
            for obj in [dat, *parent_configs]:
                if name in obj:
                    return obj[name]
            raise IndexError(f'Cannot find config value for {name}')
        self.Name = dat['Name']
        self.URL = dat['URL']
        self.folder_template = _extract_setting('FolderTemplate')
        self.subject_template = _extract_setting('SubjectTemplate')
    def __repr__(self):
        return ("{ Name: %s; URL: %s; Folder: %s; Subject: %s }" % (self.Name, self.URL, self.folder_template, self.subject_template))
    def quoted_folder(self):
        return self.folder_template.format(name=self.Name)
    def format_subject(self, subject):
        return self.subject_template.format(name=self.Name, subject=subject)


def fetch_feed_items(feed):
    l = logging.getLogger(__name__)
    l.info("Fetching feed %s", feed.URL)
    content = feedparser.parse(feed.URL)
    l.info("Done fetching feed %s", feed.URL)
    if content.bozo:
        l.warning("Feed %s had bozo set for '%s'", feed.URL, content.bozo_exception)
    for item in content.entries:
        yield FeedItem(feed, item)

def parse_configs(configs):
    l = logging.getLogger(__name__)
    feed_configs = []
    app_config = {'FolderTemplate': config.feed_folder_template, 'SubjectTemplate': config.subject_template}
    for dat in configs:
        parent_config = app_config
        l.debug("Config data: %s", dat)
        for item in filter(lambda p: p != None, yaml.safe_load_all(dat)):
            if 'Configuration' in item and 'Items' not in item:
                l.debug("Config item: %s", dat)
                parent_config = item['Configuration']
            elif 'Configuration' in item and 'Items' in item:
                parent = item['Configuration']
                for feed in item['Items']:
                    feed_configs.append(FeedConfig(feed, parent, parent_config))
            elif 'Items' in item:
                for feed in item['Items']:
                    feed_configs.append(FeedConfig(feed, parent_config))
            else:
                feed_configs.append(FeedConfig(item, parent_config))
    return feed_configs

class RssIMAP:
    def __init__(self):
        pass

    def connect_imap(self, hostname, username, password, **kwargs):
        self._W = ImapWrapper(hostname, username, password, **kwargs)
        self._W.ensure_folder(config.config_mailbox)

    def config_data_from_imap(self):
        # Don't be lazy about this.
        ret = []
        for msg in self._W.fetch_messages(config.config_mailbox, 'SUBJECT', 'rss-imap', 'NOT', 'DELETED'):
            if msg.is_multipart():
                for part in msg.get_payload():
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
        return parse_configs(the_data)

    def filter_items(self, folder, items):
        """Filter a list of items to only those that do not exist on the server."""
        try:
            have_ids = self._W.check_folder_for_message_ids(folder, [item.message_id for item in items])
        except:
            l = logging.getLogger(__name__)
            l.exception("Exception while checking existing items in %s", folder)

            try:
                have_ids = self._W.check_folder_for_message_ids(folder, [item.message_id for item in items])
            except:
                l.exception("Second exception while checking existing items in %s; skipping.", folder)
                return []
        want_items = []
        for item in items:
            if not (item.message_id.encode('utf-8') in have_ids):
                want_items.append(item)
        return want_items

    def save_item_to_imap(self, item):
        l = logging.getLogger(__name__)
        l.info('New item "%s" for feed "%s", with message_id "%s"', item.email['Subject'], item.feed.Name, item.message_id)
        self._W.append(item.feed.quoted_folder(), item.email)

    def save_items_to_imap(self, items):
        for item in items:
            self.save_item_to_imap(item)

    def disconnect(self):
        self._W.logout()


if __name__ == '__main__':
    config.configure_logging()
    # The default is to just hang forever if one of
    # the RSS feed servers isn't responding.
    socket.setdefaulttimeout(10)
    x = RssIMAP()
    x.connect_imap(config.hostname, config.username, config.password)
    feeds = x.get_feed_config_from_imap()
    todo = queue.Queue()
    producer_threads = []
    def producer(feed):
        l = logging.getLogger(__name__)
        items = list(fetch_feed_items(feed))
        if len(items) > 0:
            todo.put((feed, items))
    def consumer():
        l = logging.getLogger(__name__)
        while True:
            (feed, items) = todo.get()
            if items == None:
                break
            l.info("Filtering %d items from feed %s", len(items), feed.URL)
            filtered = x.filter_items(feed.quoted_folder(), items)
            l.info("Done filtering feed %s", feed.URL)
            if len(items) == 0:
                continue
            x.save_items_to_imap(filtered)
            l.info("Done saving %d new items from feed %s", len(filtered), feed.URL)


    consumer_thread = threading.Thread(target=consumer, name="Consumer")
    consumer_thread.start()

    for feed in feeds:
        thread = threading.Thread(target=producer, name=f"Fetch {feed.URL}", args=(feed,))
        thread.start()
        producer_threads.append(thread)
    for producer in producer_threads:
        producer.join()
    todo.put((None, None))
    consumer_thread.join()

    x.disconnect()
