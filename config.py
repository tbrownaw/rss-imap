import os, getpass

hostname = os.environ.get('IMAP_HOST')
username = os.environ.get('IMAP_USER')
password = os.environ.get('IMAP_PASS')
feed_folder_template = os.environ.get('FEED_FOLDER_TEMPLATE')

if not hostname:
    raise Error('No host name defined.')
if not username:
    raise Error('No user name defined.')
if not password:
    password = getpass.getpass()
if not feed_folder_template:
    feed_folder_template = 'RSS-combined' #'RSS/{name}'
