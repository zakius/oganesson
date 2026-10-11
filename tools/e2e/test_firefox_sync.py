"""Firefox Sync in the browser, against tools/fake_firefox_sync.py: sign-in
from settings, then bookmarks, passwords, and history sync. A bookmark edited
mid-sync keeps the edit (#39), and signing out drops held sync and sign-in
replies (#37). Firefox bookmark separators stay in Firefox. Password
changes and edits made mid-sync are retained (#258, #259); a login with empty
field names that Firefox fills keeps its leaked warning. A history deletion
made before quitting reaches Firefox after restart (#260); clearing all
history replaces saved deletions, and signed-out deletions aren't saved.

Failures: with the servers gone, syncing and signing in fail with an error
in settings, the account and local data are kept, also across a restart; a
browser folder without liboganesson_sync.so starts and shows Firefox Sync as
unavailable.

Needs the `cryptography` package, like the fake.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness import BINARY, BrowserTest, Server, wait_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import fake_firefox_sync
    from fake_firefox_sync import decrypt, encrypt
except ImportError as e:  # no cryptography package
    fake_firefox_sync = None
    MISSING = str(e)

# Finds a settings element by tag through shadow roots.
FIND = """(tag) => { const walk = (root) => { for (const el of root.querySelectorAll('*')) {
    if (el.localName === tag) return el;
    const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; } };
  return walk(document); }"""


class FirefoxSyncTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        if not fake_firefox_sync:
            raise unittest.SkipTest(f'the fake sync server needs {MISSING}')
        cls.server, base, cls.fake = fake_firefox_sync.serve()
        cls.browser_env = {'OGANESSON_FXA_SERVER': base}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.shutdown()

    def settings(self, route, tag):
        page = self.browser.new_tab('chrome://settings' + route)
        wait_for(lambda: page.eval(f'!!({FIND})({json.dumps(tag)})'), what=tag)
        return page

    def status(self, page):
        return page.eval(f"({FIND})('settings-firefox-sync').firefoxSync_")

    def sync_now(self, page):
        before = self.status(page).get('lastSync')
        page.eval("chrome.send('firefoxSyncNow')")
        wait_for(lambda: self.status(page).get('lastSync') != before and
                 not self.status(page).get('syncing'), timeout=30, what='a sync')

    def test_1_sign_in(self):
        page = self.settings('/people', 'settings-people-page')
        page.eval("chrome.send('firefoxSyncSignIn')")
        wait_for(lambda: self.status(page).get('signedIn'), timeout=30, what='the sign-in')
        wait_for(lambda: 'global' in self.fake.collections.get('meta', {}), timeout=60,
                 what='the first sync')

    def firefox_bookmarks(self):
        bundle = self.fake.bundle('bookmarks')
        records = (json.loads(decrypt(bundle, bso['payload']))
                   for bso in list(self.fake.collections.get('bookmarks', {}).values()))
        return {r['bmkUri']: r for r in records if 'bmkUri' in r}

    def test_5_bookmark_edited_during_sync(self):
        url = 'https://edited.example/'
        marks = self.browser.new_tab('chrome://bookmarks')
        wait_for(lambda: marks.eval('!!chrome.bookmarks'), what='chrome://bookmarks')
        bookmark = marks.eval("chrome.bookmarks.create({parentId: '1', title: 'Before', "
                              f"url: '{url}'}}).then(b => b.id)")
        page = self.settings('/people', 'settings-people-page')
        self.sync_now(page)
        self.assertEqual(self.firefox_bookmarks()[url]['title'], 'Before')
        # The held sync has the snapshot with Before; the edit comes after it.
        self.fake.hold('/storage/')
        page.eval("chrome.send('firefoxSyncNow')")
        wait_for(self.fake.held.is_set, timeout=30, what='the held sync')
        marks.eval(f"chrome.bookmarks.update('{bookmark}', {{title: 'After'}})")
        self.fake.let_go()
        wait_for(lambda: self.firefox_bookmarks()[url]['title'] == 'After', timeout=90,
                 what='the edit to reach Firefox')
        self.assertEqual(marks.eval(f"chrome.bookmarks.get('{bookmark}')"
                                    ".then(b => b[0].title)"), 'After')

    def firefox_record(self, bso_id):
        bso = self.fake.collections['bookmarks'][bso_id]
        return json.loads(decrypt(self.fake.bundle('bookmarks'), bso['payload']))

    def firefox_put(self, record):
        self.fake.put('bookmarks', {
            'id': record['id'],
            'payload': encrypt(self.fake.bundle('bookmarks'), json.dumps(record))},
            self.fake.now())

    def test_5b_separators_stay_in_firefox(self):
        # Firefox adds a separator at the end of Other bookmarks (unfiled).
        unfiled = self.firefox_record('unfiled')
        unfiled['children'].append('separator012')
        self.firefox_put({'id': 'separator012', 'type': 'separator', 'parentid': 'unfiled',
                          'parentName': unfiled.get('title', ''),
                          'pos': len(unfiled['children']) - 1})
        self.firefox_put(unfiled)
        page = self.settings('/people', 'settings-people-page')
        self.sync_now(page)
        # The browser doesn't show it, and a second sync keeps it in Firefox.
        marks = self.browser.new_tab('chrome://bookmarks')
        wait_for(lambda: marks.eval('!!chrome.bookmarks'), what='chrome://bookmarks')
        self.assertFalse(marks.eval(
            "chrome.bookmarks.getChildren('2').then(c => c.some(n => !n.url && !n.title))"))
        self.sync_now(page)
        self.assertIn('separator012', self.firefox_record('unfiled')['children'])

    PASSWORD_SITE = 'https://login.example'

    def passwords_page(self):
        page = self.browser.new_tab('chrome://password-manager')
        wait_for(lambda: page.eval('!!chrome.passwordsPrivate'), what='chrome://password-manager')
        return page

    def local_password(self, page, username):
        """The saved password for PASSWORD_SITE and `username`, with its id."""
        return page.eval(f"""(async () => {{
            const entry = (await chrome.passwordsPrivate.getSavedPasswordList()).find(
                e => e.username === '{username}' && e.affiliatedDomains.some(
                    d => d.signonRealm.startsWith('{self.PASSWORD_SITE}')));
            return entry && (await chrome.passwordsPrivate.requestCredentialsDetails(
                [entry.id]))[0];
        }})()""")

    def firefox_login(self, username):
        bundle = self.fake.bundle('passwords')
        for bso in list(self.fake.collections.get('passwords', {}).values()):
            record = json.loads(decrypt(bundle, bso['payload']))
            if record.get('hostname') == self.PASSWORD_SITE and record.get('username') == username:
                return record
        return None

    def firefox_change_password(self, record, password, **fields):
        record = dict(record, password=password, timePasswordChanged=int(time.time() * 1000),
                      **fields)
        self.fake.put('passwords', {
            'id': record['id'],
            'payload': encrypt(self.fake.bundle('passwords'), json.dumps(record))},
            self.fake.now())

    def test_5c_password_change_with_empty_field_names(self):
        # Added by hand, so its field names are empty.
        passwords = self.passwords_page()
        passwords.eval("chrome.passwordsPrivate.addPassword({url: "
                       f"'{self.PASSWORD_SITE}/', username: 'me', password: 'first', "
                       "note: '', useAccountStore: false})")
        page = self.settings('/people', 'settings-people-page')
        self.sync_now(page)
        record = self.firefox_login('me')
        self.assertEqual([record['password'], record['usernameField']], ['first', ''])
        # Firefox, which knows the field names, changes the password (#258).
        self.firefox_change_password(record, 'second', usernameField='user',
                                     passwordField='pass')
        self.sync_now(page)
        # The password store saves it after the sync.
        wait_for(lambda: self.local_password(passwords, 'me')['password'] == 'second',
                 what="Firefox's password")

    def test_5d_password_edited_during_sync(self):
        passwords = self.passwords_page()
        page = self.settings('/people', 'settings-people-page')
        self.firefox_change_password(self.firefox_login('me'), 'from-firefox')
        # The held sync has the snapshot with `second` and downloads Firefox's
        # change; the edit here comes after the snapshot (#259).
        self.fake.hold('/storage/')
        page.eval("chrome.send('firefoxSyncNow')")
        wait_for(self.fake.held.is_set, timeout=30, what='the held sync')
        login = self.local_password(passwords, 'me')
        passwords.eval(f"chrome.passwordsPrivate.changeCredential("
                       f"{json.dumps(dict(login, password='edited-here'))})")
        wait_for(lambda: self.local_password(passwords, 'me')['password'] == 'edited-here',
                 what='the local edit')
        self.fake.let_go()
        wait_for(lambda: self.firefox_login('me')['password'] == 'edited-here', timeout=90,
                 what='the edit to reach Firefox')
        self.assertEqual(self.local_password(passwords, 'me')['password'], 'edited-here')

    def test_5d2_note_edited_during_sync(self):
        passwords = self.passwords_page()
        page = self.settings('/people', 'settings-people-page')
        self.firefox_change_password(self.firefox_login('me'), 'firefox-again')
        self.fake.hold('/storage/')
        page.eval("chrome.send('firefoxSyncNow')")
        wait_for(self.fake.held.is_set, timeout=30, what='the held sync')
        # A note, like autofill's use count, isn't synced: Firefox's change
        # still applies.
        login = self.local_password(passwords, 'me')
        passwords.eval(f"chrome.passwordsPrivate.changeCredential("
                       f"{json.dumps(dict(login, note='a note'))})")
        wait_for(lambda: self.local_password(passwords, 'me')['note'] == 'a note',
                 what='the note')
        self.fake.let_go()
        wait_for(lambda: self.local_password(passwords, 'me')['password'] == 'firefox-again',
                 timeout=90, what="Firefox's change")
        self.sync_now(page)
        self.assertEqual(self.firefox_login('me')['password'], 'firefox-again')
        self.assertEqual(self.local_password(passwords, 'me')['password'], 'firefox-again')

    def firefox_history(self):
        bundle = self.fake.bundle('history')
        return {bso['id']: json.loads(decrypt(bundle, bso['payload']))
                for bso in list(self.fake.collections.get('history', {}).values())}

    def visit(self, path):
        """Visits `path` on a local server, and returns its URL."""
        server = Server({path: (200, {'Content-Type': 'text/html'}, b'<title>Page</title>')})
        try:
            url = server.url(path)
            tab = self.browser.new_tab(url)
            wait_for(lambda: tab.eval('document.title') == 'Page', what='the page')
            self.browser.close_target(tab)
        finally:
            server.stop()
        return url

    def delete_from_history(self, url):
        history = self.browser.new_tab('chrome://history')
        index = (f"({FIND})('history-list')?.historyData_"
                 f".findIndex(e => e.url === '{url}')")
        wait_for(lambda: history.eval(f'{index} ?? -1') >= 0, what='the page in history')
        history.eval(f"""(() => {{
            const list = ({FIND})('history-list');
            list.changeSelections_([{index}], true);
            list.deleteSelected_();
        }})()""")
        wait_for(lambda: history.eval(f'{index}') < 0, what='the deletion')
        self.browser.close_target(history)

    def saved_deletions(self):
        """The history deletions saved for the next sync, with the browser quit."""
        prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
        return prefs.get('oganesson', {}).get('firefox_sync', {}).get('history_deletions', [])

    def test_5e_history_deletion_before_quitting(self):
        url = self.visit('/gone')
        self.sync_now(self.settings('/people', 'settings-people-page'))
        guid = next(i for i, r in self.firefox_history().items() if r.get('histUri') == url)
        self.delete_from_history(url)
        # Quit well within the 30 s until the deletion's sync (#260).
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: self.firefox_history()[guid].get('deleted'), timeout=90,
                 what='the deletion to reach Firefox')

    def login_data(self, query):
        """Rows of `query` on the password store, with the browser quit."""
        with sqlite3.connect(self.browser.profile / 'Default/Login Data') as db:
            return db.execute(query).fetchall()

    def test_5f_field_names_keep_password_issue(self):
        passwords = self.passwords_page()
        passwords.eval("chrome.passwordsPrivate.addPassword({url: "
                       f"'{self.PASSWORD_SITE}/', username: 'leaked', password: 'same', "
                       "note: '', useAccountStore: false})")
        page = self.settings('/people', 'settings-people-page')
        self.sync_now(page)
        self.browser.quit()
        # Marked leaked (InsecureType::kLeaked), as a leak check would.
        with sqlite3.connect(self.browser.profile / 'Default/Login Data') as db:
            db.execute("INSERT INTO insecure_credentials (parent_id, insecurity_type, "
                       "create_time, is_muted, trigger_notification_from_backend) "
                       "SELECT id, 0, 13300000000000000, 0, 0 FROM logins "
                       "WHERE username_value = 'leaked'")
        self.browser.start()
        # Firefox fills the field names and keeps the password.
        self.firefox_change_password(self.firefox_login('leaked'), 'same',
                                     usernameField='user', passwordField='pass')
        self.sync_now(self.settings('/people', 'settings-people-page'))
        self.browser.quit()
        rows = self.login_data(
            "SELECT username_element, password_element, insecurity_type FROM logins "
            "LEFT JOIN insecure_credentials ON parent_id = logins.id "
            "WHERE username_value = 'leaked'")
        self.browser.start()
        self.assertEqual(rows, [('user', 'pass', 0)])

    def test_5g_delete_all_history_replaces_deletions(self):
        self.delete_from_history(self.visit('/before-all'))
        page = self.settings('/privacy', 'settings-privacy-page')
        # The handler replies only once initialized.
        page.eval("chrome.send('initializeClearBrowsingData', ['init'])")
        page.eval("chrome.send('clearBrowsingData', "
                  "['cbd', ['browser.clear_data.browsing_history'], 4])")  # all time
        history = self.browser.new_tab('chrome://history')
        wait_for(lambda: history.eval(f"({FIND})('history-list')?.historyData_?.length") == 0,
                 what='history to be cleared')
        # Before the deletion's sync.
        self.browser.quit()
        deletions = self.saved_deletions()
        self.browser.start()
        self.assertEqual(deletions, [{'all': True}])

    def test_5h_remote_tabs_in_history(self):
        # Another Firefox: its client record and its open tabs.
        device = 'remotefirefox01'
        client = {'id': device, 'name': 'Remote Firefox', 'type': 'desktop',
                  'fxaDeviceId': device, 'commands': [], 'version': '150.0',
                  'protocols': ['1.5']}
        tabs = {'id': device, 'clientName': 'Remote Firefox',
                'tabs': [{'title': 'Remote page', 'icon': None, 'lastUsed': 1700000000,
                          'urlHistory': ['https://remote.example/page']}]}
        for coll, record in (('clients', client), ('tabs', tabs)):
            self.fake.put(coll, {'id': device, 'payload': encrypt(
                self.fake.bundle(coll), json.dumps(record))}, self.fake.now())
        self.sync_now(self.settings('/people', 'settings-people-page'))
        history = self.browser.new_tab('chrome://history/syncedTabs')
        devices = (f"({FIND})('history-synced-device-manager')?.syncedDevices_"
                   "?.map(d => [d.device, d.tabs.map(t => t.title)])")
        wait_for(lambda: history.eval(devices) == [['Remote Firefox', ['Remote page']]],
                 timeout=30, what='the remote tab in History')
        # History's menu links to them.
        self.assertTrue(history.eval(
            f"!!({FIND})('history-side-bar').shadowRoot.querySelector('#syncedTabs')"))

    def test_5i_account_card(self):
        page = self.settings('/people', 'settings-people-page')
        self.sync_now(page)
        status = self.status(page)
        self.assertEqual((status['name'], status['email']), ('Fake User', 'fake@example.com'))
        root = f"({FIND})('settings-firefox-sync').shadowRoot"
        self.assertEqual(
            page.eval(f"{root}.querySelector('#firefoxSync .name').textContent.trim()"),
            'Fake User')
        self.assertFalse(page.eval(f"{root}.querySelector('#firefoxSyncTabs').hidden"))
        # The account's picture (the fake server's red pixel) is the profile's.
        red = (f"new Promise(done => {{ const img = new Image();"
               f" img.onload = () => {{ const c = document.createElement('canvas');"
               f" c.width = img.width; c.height = img.height;"
               f" const g = c.getContext('2d'); g.drawImage(img, 0, 0);"
               f" const [r, gr, b] = g.getImageData(img.width / 2, img.height / 2, 1, 1).data;"
               f" done(r > 200 && gr < 60 && b < 60); }};"
               f" img.onerror = () => done(false);"
               f" img.src = {root}.querySelector('#avatar').src; }})")
        wait_for(lambda: page.eval(red), timeout=30, what="the account's picture")

    def test_6_sign_out_during_sync(self):
        page = self.settings('/people', 'settings-people-page')
        # Held at its first request, so syncs run one at a time and earlier
        # ones (the tab just opened starts one) are done.
        self.fake.hold('/storage/1.5/1/info/collections')
        page.eval("chrome.send('firefoxSyncNow')")
        wait_for(self.fake.held.is_set, timeout=30, what='the held sync')
        page.eval(f"({FIND})('settings-firefox-sync').shadowRoot"
                  ".querySelector('#firefoxSyncSignOut').click()")
        wait_for(lambda: not self.status(page).get('signedIn'), what='the sign-out')
        self.fake.let_go()
        # The library signs out after the held sync, whose reply is then
        # already queued.
        wait_for(lambda: 'POST /auth/v1/account/device/destroy' in self.fake.log,
                 timeout=30, what="the sign-out's device removal")
        status = self.status(page)
        self.assertFalse(status.get('signedIn'))
        self.assertFalse(status.get('lastSync'))
        self.assertFalse(status.get('syncing'))
        self.assertEqual(status.get('name'), '')

    def test_7_sign_out_during_sign_in(self):
        page = self.settings('/people', 'settings-people-page')
        # The sign-in waits for its token.
        self.fake.hold('/auth/v1/oauth/token')
        page.eval("chrome.send('firefoxSyncSignIn')")
        wait_for(self.fake.held.is_set, timeout=30, what='the held sign-in')
        page.eval("chrome.send('firefoxSyncSignOut')")
        self.fake.let_go()
        time.sleep(5)  # for the sign-in's reply
        self.assertFalse(self.status(page).get('signedIn'))
        self.assertEqual(self.status(page).get('email'), '')

    def test_8_signed_out_deletion_not_saved(self):
        self.delete_from_history(self.visit('/signed-out'))
        self.browser.quit()
        deletions = self.saved_deletions()
        self.browser.start()
        self.assertEqual(deletions, [])



class FirefoxSyncFailuresTest(BrowserTest):
    """Steps run in order and build on each other."""
    settings = FirefoxSyncTest.settings
    status = FirefoxSyncTest.status
    sync_now = FirefoxSyncTest.sync_now
    firefox_bookmarks = FirefoxSyncTest.firefox_bookmarks
    URL = 'https://kept.example/'

    @classmethod
    def setUpClass(cls):
        if not fake_firefox_sync:
            raise unittest.SkipTest(f'the fake sync server needs {MISSING}')
        cls.server, base, cls.fake = fake_firefox_sync.serve()
        cls.browser_env = {'OGANESSON_FXA_SERVER': base}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()

    def failed_sync(self, page):
        """Syncs now; returns the error it ends with."""
        before = self.status(page).get('lastSync')
        page.eval("chrome.send('firefoxSyncNow')")
        error = wait_for(lambda: not self.status(page).get('syncing') and
                         self.status(page).get('error'), timeout=120, what='a failed sync')
        self.assertEqual(self.status(page).get('lastSync'), before)
        return error

    def bookmarked(self):
        marks = self.browser.new_tab('chrome://bookmarks')
        wait_for(lambda: marks.eval('!!chrome.bookmarks'), what='chrome://bookmarks')
        found = marks.eval(f"chrome.bookmarks.search({{url: '{self.URL}'}}).then(r => r.length)")
        self.browser.close_target(marks)
        return found == 1

    def test_1_signed_in_and_synced(self):
        page = self.settings('/people', 'settings-people-page')
        page.eval("chrome.send('firefoxSyncSignIn')")
        wait_for(lambda: self.status(page).get('signedIn'), timeout=30, what='the sign-in')
        marks = self.browser.new_tab('chrome://bookmarks')
        wait_for(lambda: marks.eval('!!chrome.bookmarks'), what='chrome://bookmarks')
        marks.eval(f"chrome.bookmarks.create({{parentId: '1', title: 'Kept', url: '{self.URL}'}})")
        self.sync_now(page)
        self.assertIn(self.URL, self.firefox_bookmarks())

    def test_2_servers_gone(self):
        type(self).server.shutdown()
        type(self).server.server_close()
        type(self).server = None
        page = self.settings('/people', 'settings-people-page')
        self.failed_sync(page)
        self.assertTrue(self.status(page).get('signedIn'))
        self.assertTrue(self.bookmarked())
        # Starting offline keeps the account.
        self.browser.quit()
        self.browser.start()
        page = self.settings('/people', 'settings-people-page')
        self.assertTrue(self.status(page).get('signedIn'))
        self.failed_sync(page)
        self.assertTrue(self.bookmarked())

    def test_3_sign_in_with_servers_gone(self):
        page = self.settings('/people', 'settings-people-page')
        page.eval("chrome.send('firefoxSyncSignOut')")
        wait_for(lambda: not self.status(page).get('signedIn'), what='the sign-out')
        page.eval("chrome.send('firefoxSyncSignIn')")
        wait_for(lambda: self.status(page).get('error'), timeout=120, what='a failed sign-in')
        self.assertFalse(self.status(page).get('signedIn'))
        self.assertTrue(self.bookmarked())

    def test_4_library_missing(self):
        # The browser's folder, linked file by file, without the library.
        folder = Path(tempfile.mkdtemp(prefix='oganesson-nosync-'))
        try:
            for entry in BINARY.parent.iterdir():
                if entry == BINARY:
                    # The binary itself, not a symlink, so its folder is this one.
                    try:
                        os.link(entry, folder / entry.name)
                    except OSError:  # another filesystem
                        shutil.copy2(entry, folder / entry.name)
                elif entry.name != 'liboganesson_sync.so':
                    (folder / entry.name).symlink_to(entry)
            self.browser.quit()
            self.browser.binary = folder / BINARY.name
            self.browser.start()
            page = self.settings('/people', 'settings-people-page')
            page.eval("chrome.send('firefoxSyncSignIn')")
            error = wait_for(lambda: self.status(page).get('error'), timeout=30,
                             what='Firefox Sync unavailable')
            self.assertIn('liboganesson_sync.so', error)
            self.assertFalse(self.status(page).get('signedIn'))
            self.assertTrue(self.bookmarked())
            self.browser.quit()
        finally:
            self.browser.binary = BINARY
            shutil.rmtree(folder)
        self.browser.start()


class FirefoxSyncServerTest(BrowserTest):
    """The account server field (#110) and the sync server field (#262),
    without OGANESSON_FXA_SERVER. Steps run in order and build on each other."""
    settings = FirefoxSyncTest.settings
    status = FirefoxSyncTest.status
    MOZILLA = 'https://accounts.firefox.com'

    @classmethod
    def setUpClass(cls):
        if not fake_firefox_sync:
            raise unittest.SkipTest(f'the fake sync server needs {MISSING}')
        cls.server, cls.base, cls.fake = fake_firefox_sync.serve()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.shutdown()
        cls.server.server_close()

    def element(self, page, selector):
        return (f"({FIND})('settings-firefox-sync').shadowRoot"
                f".querySelector({json.dumps(selector)})")

    def enter_server(self, page, text, field='#firefoxSyncServer'):
        """Types `text` in the field and commits it, as Enter or leaving it does."""
        field = self.element(page, field)
        page.eval(f"(() => {{ const f = {field}; f.value = {json.dumps(text)};"
                  " f.dispatchEvent(new Event('change')); })()")

    def saved(self):
        """The Firefox Sync prefs as saved in the profile, read with the
        browser stopped."""
        self.browser.quit()
        prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
        self.browser.start()
        return prefs['oganesson']['firefox_sync']

    def sign_in_button(self, page):
        return self.element(page, '#firefoxSync cr-button.action-button')

    def test_1_no_server_no_sign_in(self):
        page = self.settings('/people', 'settings-people-page')
        wait_for(lambda: self.status(page).get('available'), what='the status')
        self.assertEqual(self.status(page)['server'], '')
        self.assertFalse(self.status(page)['canSignIn'])
        self.assertTrue(page.eval(f"{self.sign_in_button(page)}.disabled"))
        page.eval("chrome.send('firefoxSyncSignIn')")
        wait_for(lambda: self.status(page).get('error'), what='the refusal')
        self.assertEqual(self.status(page)['error'], 'Set an account server to sign in.')
        self.assertEqual(self.fake.log, [])

    def test_1a_section_title(self):
        # The section's title doesn't use Mozilla's product name; its row says
        # what it syncs with.
        page = self.settings('/people', 'settings-people-page')
        wait_for(lambda: self.status(page).get('available'), what='the status')
        row = self.element(page, '#firefoxSync')
        self.assertEqual(page.eval(f"{row}.closest('settings-section').pageTitle"), 'Sync')
        self.assertEqual(
            page.eval(f"{row}.querySelector('.cr-padded-text > div').textContent.trim()"),
            'Sync with Firefox')

    def test_2_bare_domain(self):
        page = self.settings('/people', 'settings-people-page')
        self.enter_server(page, ' sync.example.com ')
        wait_for(lambda: self.status(page).get('server'), what='the server')
        self.assertEqual(self.status(page)['server'], 'https://sync.example.com')
        self.assertTrue(self.status(page)['canSignIn'])
        self.assertEqual(page.eval(f"{self.element(page, '#firefoxSyncServer')}.value"),
                         'https://sync.example.com')

    def test_2b_sync_server_keeps_path(self):
        page = self.settings('/people', 'settings-people-page')
        self.enter_server(page, 'storage.example.com/sync/', '#firefoxSyncStorageServer')
        wait_for(lambda: self.status(page).get('syncServer'), what='the sync server')
        self.assertEqual(self.status(page)['syncServer'], 'https://storage.example.com/sync')
        self.assertEqual(self.status(page)['server'], 'https://sync.example.com')

    def test_3_mozilla(self):
        page = self.settings('/people', 'settings-people-page')
        page.eval(f"{self.element(page, '#firefoxSyncServerRow cr-button')}.click()")
        wait_for(lambda: self.status(page).get('server') == self.MOZILLA, what='the server')
        # Mozilla's servers are its accounts and the token server they name.
        self.assertEqual(self.status(page)['syncServer'], '')
        self.assertEqual(page.eval(f"{self.element(page, '#firefoxSyncStorageServer')}.value"),
                         '')
        saved = self.saved()
        self.assertEqual(saved['server'], self.MOZILLA)
        self.assertEqual(saved.get('sync_server', ''), '')

    def test_4_sign_in(self):
        page = self.settings('/people', 'settings-people-page')
        self.enter_server(page, self.base)
        wait_for(lambda: self.status(page).get('server') == self.base, what='the server')
        page.eval(f"{self.sign_in_button(page)}.click()")
        wait_for(lambda: self.status(page).get('signedIn'), timeout=30, what='the sign-in')
        wait_for(lambda: 'global' in self.fake.collections.get('meta', {}), timeout=60,
                 what='the first sync')
        self.assertIn('GET /.well-known/fxa-client-configuration', self.fake.log)

    def test_4b_invalid_url_keeps_account(self):
        page = self.settings('/people', 'settings-people-page')
        self.assertTrue(self.status(page)['signedIn'])
        self.enter_server(page, 'https://sync.example.com:99999')
        wait_for(lambda: self.status(page).get('error'), what='the refusal')
        self.assertEqual(self.status(page)['error'],
                         'Not a server URL: https://sync.example.com:99999')
        self.assertTrue(self.status(page)['signedIn'])
        self.assertEqual(self.status(page)['server'], self.base)
        # The status update leaves the typed text in the field.
        self.assertEqual(page.eval(f"{self.element(page, '#firefoxSyncServer')}.value"),
                         'https://sync.example.com:99999')

    def test_5_new_server_signs_out(self):
        page = self.settings('/people', 'settings-people-page')
        self.assertTrue(self.status(page)['signedIn'])
        self.enter_server(page, 'https://sync.example.com/path')
        wait_for(lambda: not self.status(page).get('signedIn'), what='the sign-out')
        self.assertEqual(self.status(page)['server'], 'https://sync.example.com')
        self.assertEqual(self.status(page)['email'], '')
        saved = self.saved()
        self.assertEqual(saved['server'], 'https://sync.example.com')
        self.assertNotIn('secrets', saved)

    def test_6_signed_in_profile_gets_mozilla(self):
        # A profile signed in before the setting existed: an account, no server.
        self.browser.quit()
        path = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(path.read_text())
        prefs['oganesson']['firefox_sync'].pop('server', None)
        prefs['oganesson']['firefox_sync']['secrets'] = 'djEw'
        path.write_text(json.dumps(prefs))
        self.browser.start()
        page = self.settings('/people', 'settings-people-page')
        wait_for(lambda: self.status(page).get('available'), what='the status')
        self.assertEqual(self.status(page)['server'], self.MOZILLA)

    def test_7_self_hosted_sync_server(self):
        # Accounts from one server, storage from another one's token server,
        # as Mozilla's accounts with a self-hosted syncstorage-rs.
        storage_server, storage_base, storage = fake_firefox_sync.serve()
        self.addClassCleanup(storage_server.server_close)
        self.addClassCleanup(storage_server.shutdown)
        page = self.settings('/people', 'settings-people-page')
        self.enter_server(page, self.base)
        wait_for(lambda: self.status(page).get('server') == self.base, what='the server')
        self.enter_server(page, storage_base + '/token/1.0/sync/1.5',
                          '#firefoxSyncStorageServer')
        wait_for(lambda: self.status(page).get('syncServer'), what='the sync server')
        self.fake.log.clear()
        self.fake.collections.clear()
        page.eval(f"{self.sign_in_button(page)}.click()")
        wait_for(lambda: self.status(page).get('signedIn'), timeout=30, what='the sign-in')
        wait_for(lambda: 'global' in storage.collections.get('meta', {}), timeout=60,
                 what='the first sync')
        self.assertIn('GET /token/1.0/sync/1.5', storage.log)
        self.assertNotIn('GET /token/1.0/sync/1.5', self.fake.log)
        self.assertEqual(self.fake.collections, {})
        self.assertNotIn('GET /.well-known/fxa-client-configuration', storage.log)

    def test_8_new_sync_server_signs_out(self):
        page = self.settings('/people', 'settings-people-page')
        self.assertTrue(self.status(page)['signedIn'])
        self.enter_server(page, '', '#firefoxSyncStorageServer')
        wait_for(lambda: not self.status(page).get('signedIn'), what='the sign-out')
        self.assertEqual(self.status(page)['syncServer'], '')
        self.assertEqual(self.status(page)['server'], self.base)
        saved = self.saved()
        self.assertEqual(saved.get('sync_server', ''), '')
        self.assertNotIn('secrets', saved)

    def test_9_not_an_accounts_server(self):
        # A sync storage server in the account field: no fxa-client-configuration.
        storage = Server({})
        try:
            page = self.settings('/people', 'settings-people-page')
            self.enter_server(page, storage.url('/'))
            origin = storage.url('/').rstrip('/')
            wait_for(lambda: self.status(page).get('server') == origin, what='the server')
            pages = lambda: [t for t in self.browser.targets() if t['type'] == 'page']
            tabs = len(pages())
            page.eval(f"{self.sign_in_button(page)}.click()")
            error = wait_for(lambda: self.status(page).get('error'), timeout=30,
                             what='the failed sign-in')
            self.assertEqual(error, f"{origin} isn't a Mozilla accounts server, or can't be "
                             "reached. A self-hosted sync storage server goes in Sync server.")
            self.assertIn('/.well-known/fxa-client-configuration', storage.requests)
            self.assertFalse(self.status(page)['signedIn'])
            self.assertEqual(len(pages()), tabs)
            # Shown on the settings page, which stays in front.
            self.assertEqual(
                page.eval(f"{self.element(page, '#firefoxSync .secondary')}.textContent"),
                error)
        finally:
            storage.stop()


if __name__ == '__main__':
    unittest.main()
