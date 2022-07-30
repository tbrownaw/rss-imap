import pprint
import textwrap
import unittest

import config
import rss_imap

#config.configure_logging()



class TestRssImap(unittest.TestCase):
  def test_load_from_imap(self):
    x = rss_imap.RssIMAP()
    x.connect_imap(config.hostname, config.username, config.password, ssl=not config.debug_no_imap_ssl)

    feeds = x.get_feed_config_from_imap()
    #x.save_items_to_imap(x.filter_items(x.fetch_all_feed_items()))
    x.disconnect()

    for feed in feeds:
        pprint.pprint(feed)

  def test_load_feed_definitions(self):
    result = "\n"
    for feed in rss_imap.parse_configs([textwrap.dedent(x) for x in ["""
    Configuration:
      FolderTemplate: 'BaseFolderTemplate'
      SubjectTemplate: 'BaseSubjectTemplate'
    Items:
    - Name: Foo
      URL: https://foo
    - Name: Bar
      URL: https://bar
      FolderTemplate: 'Folder{template}'
      SubjectTemplate: 'Subject For {name}'
    ---
    Configuration:
      FolderTemplate: FolderTemplateTwo
      SubjectTemplate: SubjectTemplateTwo
    ---
    Configuration:
      FolderTemplate: TTT
      SubjectTemplate: SSS
    Items:
    - Name: FooThree
      URL: https://FooThree
    ---
    Items:
    - Name: FooTwo
      URL: https://FooTwo
    """, """
    Name: Separate
    URL: https://separate
    """]]):
        result += str(feed) + "\n"

    expected = textwrap.dedent("""
    { Name: Foo; URL: https://foo; Folder: BaseFolderTemplate; Subject: BaseSubjectTemplate }
    { Name: Bar; URL: https://bar; Folder: Folder{template}; Subject: Subject For {name} }
    { Name: FooThree; URL: https://FooThree; Folder: TTT; Subject: SSS }
    { Name: FooTwo; URL: https://FooTwo; Folder: FolderTemplateTwo; Subject: SubjectTemplateTwo }
    { Name: Separate; URL: https://separate; Folder: RSS Feeds/{name}; Subject: {subject} }
    """)

    self.assertEqual(result, expected)

  def test_extract_feed_items(self):
    feeds = rss_imap.parse_configs(["""
    Configuration:
      FolderTemplate: 'TargetFolder'
      SubjectTemplate: '{name}: {subject}'
    Items:
    - Name: TestFeed
      URL: './TestFeed.xml'
    """])
    self.assertEqual(len(feeds), 1)
    feed = feeds[0]
    items = list(rss_imap.fetch_feed_items(feed))
    self.assertEqual(len(items), 1)
    item = items[0]
    self.assertEqual(item.message_id, "urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a")


if __name__ == '__main__':
  unittest.main(verbosity=2)
