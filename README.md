RSS -> IMAP Bridge
==================

Import RSS feeds into a set of IMAP folders. The list of feeds (and which
folder names to put the items in) is read from the IMAP server. The only
configuration that needs to live in the same place as this is run from, is
the IMAP server connection / login information.

Configuration
-------------

The default config.py expects 3 environment variables:

*   IMAP_HOST -- Hostname of the IMAP server to use.
*   IMAP_USER -- Username to log in as.
*   IMAP_PASS -- Password to use.

There isn't (currently) a way to specify a non-SSL connection, or to
specify a non-standard port.

Feed Definitions
----------------

This reads feed definitions from the IMAP server. They're expected to be in
messages with "rss-imap" in the subject line, in a ".config" folder.

They can either be in attachments with "Folders" in the name, or in
non-multipart messages. ((FIXME: needs to also look in the body of multipart
messages, at least if they're plain text))

The feed configurations are a list of Yaml items, with two keys:

    Folder Name: "Lambda the Ultimate - Programming Languages Weblog"
    Feed URL: http://lambda-the-ultimate.org/rss.xml
    ---
    Folder Name: "LWN.net"
    Feed URL: http://lwn.net/headlines/newrss

*   "Name" is the name of the subfolder under RSS/ that the feed items go in.
*   "URL" is what it says, the URL to fetch the RSS feed from.

Setup
-----

This assumes Python3, and uses PyYaml and Universal Feed Parser.

    virtualenv -p $(which python3) $DIR
    . $DIR/bin/activate
    pip3 install feedparser
    pip3 install pyyaml
    # Edit config.py or set IMAP_HOST, IMAP_USER, and IMAP_PASS
