import config
import rss_imap

x = rss_imap.RssIMAP()
x.connect_imap(config.hostname, config.username, config.password)
x.save_items_to_imap(x.filter_items(x.fetch_all_feed_items()))
x.disconnect()
