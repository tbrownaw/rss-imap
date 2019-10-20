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
    def __init__(self, host, user, pw):
        self.M = IMAPClient(host)
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
        search_name = name[:-1] if name.endswith('/') else name
        if not any(n == search_name for n in self.folder_list):
            typ, dtl = self.M.create_folder(name)
            if typ != "OK":
                raise IMAPError("Could not create folder: %s" % dtl)
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

    def have_message_with_id(self, folder, msgid):
        self.select_folder(folder)
        res = self.M.search(['HEADER', 'Message-Id', msgid, 'NOT', 'DELETED'])
        return any(res)

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

