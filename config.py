import os, getpass

hostname = os.environ.get('IMAP_HOST')
username = os.environ.get('IMAP_USER')
password = os.environ.get('IMAP_PASS')

# Can be overridden by:
# Configuration:
#   FolderTemplate: 'template with {name}'
#   SubjectTemplate: 'template with {name} and {subject}'
feed_folder_template = os.environ.get('FEED_FOLDER_TEMPLATE')
subject_template = os.environ.get('FEED_ITEM_SUBJECT_TEMPLATE')

if not hostname:
    raise Error('No host name defined.')
if not username:
    raise Error('No user name defined.')
if not password:
    password = getpass.getpass()
if not feed_folder_template:
    feed_folder_template = 'RSS-combined' #'RSS/{name}'
if not subject_template:
    subject_template = '{subject}'
