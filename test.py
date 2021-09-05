import pprint

import config
import rss_imap

config.configure_logging()

x = rss_imap.RssIMAP()
x.connect_imap(config.hostname, config.username, config.password, ssl=False)

feeds = x.get_feed_config_from_imap()
#x.save_items_to_imap(x.filter_items(x.fetch_all_feed_items()))
x.disconnect()

for feed in feeds:
    pprint.pprint(feed)


#####
print("\n##########\n")
for feed in rss_imap.parse_configs(["""
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
"""]):
    pprint.pprint(feed)