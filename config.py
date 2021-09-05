import os, getpass, logging

hostname = os.environ.get('IMAP_HOST')
username = os.environ.get('IMAP_USER')
password = os.environ.get('IMAP_PASS')

config_mailbox = os.environ.get('CONFIG_MAILBOX') or '.config'

# Can be overridden by:
# Configuration:
#   FolderTemplate: 'template with {name}'
#   SubjectTemplate: 'template with {name} and {subject}'
feed_folder_template = os.environ.get('FEED_FOLDER_TEMPLATE') or 'RSS Feeds/{name}'
subject_template = os.environ.get('FEED_ITEM_SUBJECT_TEMPLATE') or '{subject}'

if not hostname:
    raise Exception('No host name defined.')
if not username:
    raise Exception('No user name defined.')
if not password:
    password = getpass.getpass()
if not feed_folder_template:
    feed_folder_template = 'RSS-combined' #'RSS/{name}'
if not subject_template:
    subject_template = '{subject}'

def configure_logging():
    logging.basicConfig(format="%(asctime)s > %(name)s > %(levelname)s > %(message)s", level=logging.INFO)
