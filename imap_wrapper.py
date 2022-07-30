import email
import logging
import re

from imapclient import IMAPClient

class IMAPError(IOError):
    pass

class ImapWrapper:
    """A wrapper around imaplib, since that's a bit
    lower-level than I'd prefer to work with."""

    #This regex is:
    # list of flags in parens
    # quoted delimiter
    # possible-quoted folder name
    list_matcher = re.compile(r'^\(([^()]*)\) "([^"]*)" (([^" ]+)|"([^"]*)")$')
    def __init__(self, host, user, pw, **kwargs):
        """kwargs: Paassed through to IMAPClient"""
        self.M = IMAPClient(host, **kwargs)
        self.M.login(user, pw)
        self._selected_folder = None
        self._update_folders()

    def logout(self):
        self.M.logout()

    def _update_folders(self):
        listing = self.M.list_folders()
        self.folder_list = [name for (flags, delim, name) in listing]

    def ensure_folder(self, name):
        """Return True if the folder was created, False if it already existed."""
        l = logging.getLogger(__name__)
        search_name = name[:-1] if name.endswith('/') else name
        if not any(n == search_name for n in self.folder_list):
            rslt = self.M.create_folder(name)
            l.info(f"Folder create result: {rslt}")
            self.folder_list.append(search_name)
            return True
        else:
            return False

    def fetch_messages(self, folder, *search_args):
        l = logging.getLogger(__name__)
        ret = []
        self.select_folder(folder)
        message_ids = self.M.search(search_args)
        message_dict = self.M.fetch(message_ids, 'RFC822')
        for msg in message_dict.values():
            l.debug("Got message: %s", msg)
            msg = email.message_from_string(msg[b'RFC822'].decode('UTF-8'))
            ret.append(msg)

        return ret
    
    def check_folder_for_message_ids(self, folder, msgids):
        self.select_folder(folder)
        search_ids = []
        for msgid in msgids:
            if len(search_ids) > 0:
                search_ids.insert(0, 'OR')
            search_ids.append(['HEADER', 'Message-Id', msgid])
        message_numbers = self.M.search(['NOT', 'DELETED', search_ids])
        message_envelopes = self.M.fetch(message_numbers, 'ENVELOPE')
        have_ids = []
        for msgdata in message_envelopes.values():
            try:
                envelope = msgdata[b'ENVELOPE']
                have_ids.append(envelope.message_id)
            except Exception as e:
                logging.getLogger(__name__).error("Error looking up existing message ID: %s", e, exc_info=1)
        return have_ids

    def append(self, folder_name, email):
        response = self.M.append(folder_name, str(email).encode('utf-8'))
        logging.getLogger(__name__).debug("Append response: %s", response)

    # FIXME sets the context folder
    def select_folder(self, name):
        if self._selected_folder == name:
            return
        dtl = self.M.select_folder(name)
        logging.getLogger(__name__).debug("select_folder = %s", dtl)
        self._selected_folder = name

    def create_subscribe_folder(self, name):
        created = self.ensure_folder(name)
        if created:
            res = self.M.subscribe_folder(name)
            logging.getLogger(__name__).debug("Subscribe result: %s", res)

