import email
import imaplib
import re

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
        self.M = imaplib.IMAP4_SSL(host)
        self.M.login(user, pw)
        self._selected_folder = None
        self._update_folders()
    def logout(self):
        self.M.logout()
    def _update_folders(self):
        def extract_names(ll):
            for ent in ll:
                m = self.list_matcher.match(ent.decode('US-ASCII'))
                if m:
                    if m.group(4) == None:
                        yield m.group(5)
                    else:
                        yield m.group(4)
                else:
                    raise IMAPError("Could not extract folder name from %s" % ent)
        typ, listing = self.M.list()
        if typ != "OK":
            raise IMAPError("Failed to list folders: %s" % listing)
        self.folder_list = list(extract_names(listing))
    def ensure_folder(self, name):
        """Return True if the folder was created, False if it already existed."""
        search_name = name[:-1] if name.endswith('/') else name
        if not any(n == search_name for n in self.folder_list):
            typ, dtl = self.M.create('"' + name + '"')
            if typ != "OK":
                raise IMAPError("Could not create folder: %s" % dtl)
            self.folder_list.append(search_name)
            return True
        else:
            return False
    # FIXME uses the context folder
    def search(self, *args):
        try:
            typ, listing = self.M.search(None, *args)
        except:
            raise IMAPError('Search failed with args "%s"' % str(args))
        if typ != "OK":
            raise IMAPError('search() failed: %s' % listing)
        for lst in listing:
            dd = lst.decode('US-ASCII')
            for m in dd.split(' '):
                if m:
                    yield m

    def fetch_messages(self, folder, *search_args):
        ret = []
        self.select_folder(folder)
        for num in self.search(*search_args):
            typ, dat = self.M.fetch(num, '(RFC822)')
            if typ != "OK":
                raise IMAPError('Could not fetch searched message: %s' % dat)
            msg = email.message_from_string(dat[0][1].decode('UTF-8'))
            ret.append(msg)
        ret.reverse()
        return ret

    def have_message_with_id(self, folder, msgid):
        self.select_folder(folder)
        res = list(self.search('HEADER', 'Message-Id', msgid, 'NOT', 'DELETED'))
        return any(res)

    def append(self, folder_name, email):
        typ, detail = self.M.append('"' + folder_name + '"', '', '', str(email).encode('utf-8'))
        if typ != 'OK':
            raise IMAPError('Could not add item: %s' % detail)

    # FIXME sets the context folder
    def select_folder(self, name):
        if self._selected_folder == name:
            return
        typ, dtl = self.M.select('"' + name + '"')
        if typ != "OK":
            raise IMAPError('Could not select folder "%s": %s' % (name, dtl))
        self._selected_folder = name

    def create_subscribe_folder(self, name):
        created = self.ensure_folder(name)
        if created:
            typ, dtl = self.M.subscribe('"' + name + '"')
            if typ != "OK":
                raise IMAPError("Could not subscribe to folder %s" % name)

