"""Settings → Privacy's switches that stop saving history: each sets its
pref; with browsing history off, Firefox Sync's history switch is off and
greyed out, and back on when it is; with download history off, a download
isn't in the History database after quitting, while one from before is.
While browsing history isn't saved, a closed tab can still be reopened, as
long as the switch that keeps closed tabs in memory is on.
"""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from harness import BrowserTest, Server, wait_for
from test_firefox_sync import FIND

# Reads and restores recently closed tabs: chrome.sessions goes through the
# same TabRestoreService as Ctrl+Shift+T.
MANIFEST = {'manifest_version': 3, 'name': 'History saving test', 'version': '1',
            'permissions': ['tabs', 'sessions'],
            'background': {'service_worker': 'background.js'}}


class HistorySavingTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.downloads = Path(tempfile.mkdtemp(prefix='oganesson-downloads-'))
        cls.extension = Path(tempfile.mkdtemp(prefix='oganesson-history-saving-'))
        (cls.extension / 'manifest.json').write_text(json.dumps(MANIFEST))
        (cls.extension / 'background.js').write_text('')
        cls.browser_args = (f'--load-extension={cls.extension}',)
        cls.prefs = {'download': {'default_directory': str(cls.downloads),
                                  'prompt_for_download': False}}
        cls.server = Server({f'/{name}': (200, {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': f'attachment; filename="{name}"'}, b'data')
            for name in ('kept.bin', 'unsaved.bin')} | {
                '/closed.html': (200, {'Content-Type': 'text/html'}, b'<title>closed</title>')})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.downloads)
        shutil.rmtree(cls.extension)

    def privacy(self):
        page = self.browser.new_tab('chrome://settings/privacy')
        wait_for(lambda: page.eval(f"!!({FIND})('settings-history-saving')"),
                 what='the history switches')
        return page

    def pref(self, page, name):
        page.eval(f"chrome.settingsPrivate.getPref({json.dumps(name)})"
                  ".then(p => window.lastPref = p.value)")
        wait_for(lambda: page.eval('window.lastPref !== undefined'), what=name)
        value = page.eval('window.lastPref')
        page.eval('delete window.lastPref')
        return value

    def toggle(self, page, switch):
        page.eval(f"({FIND})('settings-history-saving').shadowRoot"
                  f".querySelector('#{switch}').click()")

    def sync_history(self, page):
        types = page.eval(f"({FIND})('settings-firefox-sync').firefoxSync_.types") or []
        return next(t for t in types if t['name'] == 'history')

    def download(self, name):
        # A tab opened only for a download closes itself.
        self.browser.new_tab(self.server.url(f'/{name}'))
        wait_for(lambda: (self.downloads / name).exists(), what=name)

    def test_1_browsing_history_switch_blocks_history_sync(self):
        page = self.privacy()
        self.assertFalse(self.pref(page, 'history.saving_disabled'))
        self.toggle(page, 'browsingHistory')
        wait_for(lambda: self.pref(page, 'history.saving_disabled'), what='the pref')

        sync = self.browser.new_tab('chrome://settings/autofill')
        wait_for(lambda: sync.eval(
            f"!!({FIND})('settings-firefox-sync')?.firefoxSync_?.types"), what='Sync types')
        history = self.sync_history(sync)
        self.assertTrue(history['blocked'])
        self.assertFalse(history['enabled'])

        self.toggle(page, 'browsingHistory')
        wait_for(lambda: not self.sync_history(sync).get('blocked'), what='history sync back')
        self.assertTrue(self.sync_history(sync)['enabled'])
        self.assertFalse(self.pref(page, 'history.saving_disabled'))

    def test_2_download_history_switch(self):
        self.download('kept.bin')
        page = self.privacy()
        self.toggle(page, 'downloadHistory')
        wait_for(lambda: self.pref(page, 'oganesson.downloads.saving_disabled'),
                 what='the pref')
        self.download('unsaved.bin')
        # The History database is written by the time the browser quits.
        self.browser.quit()
        with sqlite3.connect(self.browser.profile / 'Default/History') as db:
            saved = {Path(row[0]).name for row in db.execute('SELECT target_path FROM downloads')}
        self.browser.start()
        self.assertEqual(saved, {'kept.bin'})

    def run_js(self, body):
        page = self.browser.page('background.js')
        wait_for(lambda: page.eval('typeof chrome.sessions') == 'object', what='the extension APIs')
        return page.eval(f'(async () => {{ {body} }})()')

    def close_and_reopen(self):
        """Whether a tab closed just now can be reopened."""
        url = self.server.url('/closed.html')
        return self.run_js(f"""
            const url = {json.dumps(url)};
            const tab = await chrome.tabs.create({{url}});
            while ((await chrome.tabs.get(tab.id)).status !== 'complete')
                await new Promise(r => setTimeout(r, 100));
            await chrome.tabs.remove(tab.id);
            const closed = await chrome.sessions.getRecentlyClosed();
            if (!closed.length || closed[0].tab?.url !== url) return false;
            const restored = await chrome.sessions.restore();
            await chrome.tabs.remove(restored.tab.id);
            return true;""")

    def test_3_closed_tabs_in_memory(self):
        page = self.privacy()
        switch = f"({FIND})('settings-history-saving').shadowRoot.querySelector('#keepClosedTabs')"
        self.assertTrue(page.eval(f'{switch}.hidden'))
        self.assertTrue(self.close_and_reopen(), 'with history saved')
        self.toggle(page, 'browsingHistory')
        wait_for(lambda: self.pref(page, 'history.saving_disabled'), what='the pref')
        wait_for(lambda: not page.eval(f'{switch}.hidden'), what='the closed tabs switch')
        self.assertTrue(self.pref(page, 'oganesson.history.keep_closed_tabs'))
        self.assertTrue(self.close_and_reopen(), 'kept in memory')

        self.toggle(page, 'keepClosedTabs')
        wait_for(lambda: not self.pref(page, 'oganesson.history.keep_closed_tabs'),
                 what='the pref')
        self.assertFalse(self.close_and_reopen(), 'kept nowhere')
        self.toggle(page, 'keepClosedTabs')
        self.toggle(page, 'browsingHistory')


if __name__ == '__main__':
    unittest.main()
