import getpass, imaplib, re

hostname = "prjek.net"
username = "tbrownaw"
M = imaplib.IMAP4_SSL(hostname)
M.login(username, getpass.getpass())



list_matcher = re.compile('^\(([^()]*)\) "([^"]*)" "([^"]*)"$')
def list_folders():
    def extract_names(ll):
        for ent in ll:
            m = list_matcher.match(ent.decode('US-ASCII'))
            if m:
                yield m.group(3)
            else:
                yield '!!!' + ("%s" % ent)
    typ, listing = M.list()
    #print(typ, listing)
    # There has got to be a better way to do this.
    for x in extract_names(listing):
        yield x




names = list(list_folders())

if not any(f == '.config' for f in names):
    print('Creating .config folder')
    M.create('.config')
if not any(f == 'RSS' for f in names):
    print('Creating toplevel RSS folder')
    M.create('RSS/')

for nn in names:
    print("Folder: " + nn)

# M.create('.config')
# M.create('RSS/')

M.select('.config')

M.logout()
