"""What the WebExtensions climb adds is Firefox add-ons' alone (dubna's
webextensions/README.md, "Firefox add-ons only"): a Chrome Web Store extension
that tells Chrome from Firefox by what it sees takes its Chrome path.

One probe runs in three extensions of the same files: a Chrome extension
(unpacked, without a gecko key), a Firefox add-on (unpacked, with one) and a
.crx with a gecko key from the Chrome Web Store's update server, which counts as
Chrome's. The probe covers each kind of mark in the schemas: a member, a
namespace, an argument, an enum value, a result property, and the features
that Firefox add-ons have in Manifest V2.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import BINARY, BrowserTest, Server, extension_id, wait_for
from test_webstore_updates import UPDATE_HOST, UPDATE_PATH, extension_id as key_id

PERMISSIONS = ['tabs', 'contextMenus', 'cookies', 'bookmarks', 'proxy', 'privacy', 'storage',
               'scripting', 'browserSettings', 'contextualIdentities', 'https://example.com/*']
MANIFEST = {'manifest_version': 2, 'name': 'Firefox add-ons only', 'version': '1.0',
            'background': {'scripts': ['probe.js']}, 'browser_action': {},
            'permissions': PERMISSIONS}
GECKO = {'browser_specific_settings': {'gecko': {'id': 'only@example.com'}}}
# Paths under chrome. that only a Firefox add-on has.
MEMBERS = ['runtime.getBrowserInfo', 'runtime.getDocumentId', 'i18n.getPreferredSystemLanguages',
           'proxy.onRequest', 'proxy.onError', 'contextMenus.onShown', 'contextMenus.onHidden',
           'contextMenus.refresh', 'contextMenus.ContextType.PASSWORD', 'contextMenus.ViewType',
           'browserAction.setBadgeTextColor', 'browserAction.getUserSettings',
           'browserAction.isEnabled', 'privacy.network.peerConnectionEnabled', 'theme', 'menus',
           'contentScripts', 'storage.session', 'scripting', 'browserSettings',
           'contextualIdentities']
# Calls that throw in Chromium, as their first argument check does, and work for a Firefox
# add-on.
CALLS = {
    'contextMenus.create icons': "chrome.contextMenus.create({id: 'a', title: 'a', icons: {}})",
    'contextMenus.create password':
        "chrome.contextMenus.create({id: 'b', title: 'b', contexts: ['password']})",
    'browserAction.setTitle null': 'chrome.browserAction.setTitle({title: null})',
    'browserAction.setTitle windowId': "chrome.browserAction.setTitle({title: 'x', windowId: -2})",
    'cookies.getAll firstPartyDomain': 'chrome.cookies.getAll({firstPartyDomain: null})',
    'tabs.create discarded': "chrome.tabs.create({url: 'about:blank', discarded: true})",
    'tabs.onUpdated filter':
        "chrome.tabs.onUpdated.addListener(() => {}, {properties: ['status']})",
}
# Result properties that only a Firefox add-on gets.
RESULTS = {
    'Tab.cookieStoreId': "'cookieStoreId' in (await chrome.tabs.query({}))[0]",
    'Cookie.firstPartyDomain': """'firstPartyDomain' in await chrome.cookies.set(
        {url: 'https://example.com/', name: 'n', value: 'v'})""",
}
# Written out as functions: an extension page's CSP has no eval.
PROBE = """
const calls = {%s};
const results = {%s};
self.probe = async () => {
  const result = {};
  for (const path of %s) {
    let object = chrome;
    result[path] = path.split('.').every(key => {
      const found = object != null && key in Object(object);
      object = found ? object[key] : undefined;
      return found;
    });
  }
  for (const [name, call] of Object.entries(calls)) {
    try {
      call();
      result[name] = 'ok';
    } catch (error) {
      result[name] = 'throws';
    }
  }
  for (const [name, read] of Object.entries(results)) {
    result[name] = await read();
  }
  return result;
};
""" % (', '.join(f'{json.dumps(name)}: () => {call}' for name, call in CALLS.items()),
       ', '.join(f'{json.dumps(name)}: async () => {expression}'
                 for name, expression in RESULTS.items()),
       json.dumps(MEMBERS))
FIREFOX = {**{path: True for path in MEMBERS}, **{name: 'ok' for name in CALLS},
           **{name: True for name in RESULTS}}
CHROMIUM = {**{path: False for path in MEMBERS}, **{name: 'throws' for name in CALLS},
            **{name: False for name in RESULTS}}


class FirefoxAddOnsOnlyTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-firefox-only-'))
        cls.chrome, cls.firefox, packed = (cls.folder / name for name in
                                           ('chrome', 'firefox', 'packed'))
        for folder, manifest in ((cls.chrome, MANIFEST), (cls.firefox, {**MANIFEST, **GECKO}),
                                 (packed, {**MANIFEST, **GECKO,
                                           'update_url': f'https://{UPDATE_HOST}{UPDATE_PATH}'})):
            folder.mkdir()
            (folder / 'manifest.json').write_text(json.dumps(manifest))
            (folder / 'probe.js').write_text(PROBE)
        cert, key, packed_key = (cls.folder / name for name in
                                 ('cert.pem', 'key.pem', 'packed-key.pem'))
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', f'/CN={UPDATE_HOST}', '-addext', f'subjectAltName=DNS:{UPDATE_HOST}',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-out', str(packed_key)], check=True,
                       capture_output=True)
        subprocess.run([str(BINARY), f'--pack-extension={packed}',
                        f'--pack-extension-key={packed_key}', '--no-message-box',
                        f'--user-data-dir={cls.folder / "pack-profile"}'],
                       check=True, capture_output=True, timeout=60)
        cls.packed_id = key_id(packed_key)
        update = (f'<?xml version="1.0" encoding="UTF-8"?>'
                  f'<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">'
                  f'<app appid="{cls.packed_id}" status="ok"><updatecheck status="ok" '
                  f'version="1.0" codebase="https://{UPDATE_HOST}/packed.crx"/></app>'
                  f'</gupdate>').encode()
        cls.server = Server({UPDATE_PATH: (200, {'Content-Type': 'text/xml'}, update),
                             '/packed.crx': (200, {'Content-Type': 'application/x-chrome-extension'},
                                             (cls.folder / 'packed.crx').read_bytes())},
                            tls=(str(cert), str(key)))
        cls.browser_args = (f'--load-extension={cls.chrome},{cls.firefox}',
                            f'--host-resolver-rules=MAP {UPDATE_HOST} 127.0.0.1:{cls.server.port}',
                            '--ignore-certificate-errors')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def probe(self, extension):
        page = self.browser.extension_background(extension, timeout=30)
        wait_for(lambda: page.eval('typeof self.probe') == 'function', what='the probe')
        return page.eval('self.probe()')

    def test_firefox_add_on(self):
        self.assertEqual(self.probe(extension_id(self.firefox)), FIREFOX)

    def test_chrome_extension(self):
        self.assertEqual(self.probe(extension_id(self.chrome)), CHROMIUM)

    def test_crx_with_a_gecko_key(self):
        self.browser.quit()
        folder = self.browser.profile / 'External Extensions'
        folder.mkdir(exist_ok=True)
        (folder / f'{self.packed_id}.json').write_text(json.dumps(
            {'external_update_url': f'https://{UPDATE_HOST}{UPDATE_PATH}'}))
        self.browser.start()
        wait_for(lambda: (self.browser.profile / 'Default/Extensions' / self.packed_id).is_dir(),
                 timeout=60, what='the .crx installed from the update server')
        self.assertEqual(self.probe(self.packed_id), CHROMIUM)


if __name__ == '__main__':
    unittest.main()
