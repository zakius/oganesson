"""The WebExtensions climb's corpus runner (corpus.py): small add-ons of each
kind it tells apart get the levels it gives them. Each installs from its .xpi
with the Gecko ID that test_levels() gives it, but where it has a
browser_specific_settings of its own, signed by the test root that the
browser trusts, as AMO signs its add-ons (zakius/dubna#219)."""

import json
import tempfile
import unittest
from pathlib import Path

import corpus
from harness import amo_signed, signature_root_arg, zipped

BACKGROUND_MV2 = {'manifest_version': 2, 'name': 'probe', 'version': '1',
                  'background': {'scripts': ['background.js']}}
KEY = ('MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDJnRbHexNTjRkPiiY/aArVJM+iKGwGLV6K7ivyrBfl1hwn8'
       'AjDF2aD2+1AsxJ2LeZL8z7FxJ7WPxJAoIyCfMOULQPV9LJ8Pq8egUMcC5YKvZN4rpIuEvLvWdAtwZlcFj6K2+'
       'Tlq8b5NE5Aj3BJwfRQVHtfdYj92BuW9zflWZPMDwIDAQAB')
# The keyed add-on's ID: from its Gecko ID, as the .xpi install makes it, not
# from KEY, as --load-extension would.
KEYED_ID = corpus.installed_id(Path('/nonexistent'), {'browser_specific_settings': {
    'gecko': {'id': 'keyed@corpus.test'}}})
POPUP = {'browser_action': {'default_popup': 'popup.html'}}
CONTENT = {'content_scripts': [{'matches': ['https://*.example.org/*'], 'js': ['content.js']}]}
# Each add-on: its manifest (text or JSON), background.js, the level, and its
# other files.
ADDONS = {
    'works': (BACKGROUND_MV2, 'self.started = true;', 'L3'),
    'firefox-metadata': ({**BACKGROUND_MV2, 'browser_specific_settings': {
        'gecko': {'id': 'probe@example.org'}}}, 'self.started = true;', 'L3'),
    # Its ID comes from its Gecko ID, not from the key.
    'keyed': ({**BACKGROUND_MV2, 'key': KEY}, 'self.started = true;', 'L3'),
    # Its error names the keyed add-on's page, which keeps that one at L2.
    'names-another': (BACKGROUND_MV2,
                      f"throw new Error('cannot reach chrome-extension://{KEYED_ID}/page.html');",
                      'L1'),
    # Chromium's refusal of another add-on's page, which Firefox refuses too,
    # and of its own page, which Firefox allows.
    'other-add-on-page': (BACKGROUND_MV2, 'throw new Error(\'Cannot access contents of url '
                          f'"chrome-extension://{KEYED_ID}/page.html".\');', 'L3'),
    'own-page': (BACKGROUND_MV2, 'throw new Error(\'Cannot access contents of url '
                 '"chrome-extension://\' + chrome.runtime.id + \'/page.html".\');', 'L1'),
    # A dotted permission that Chromium has.
    'dotted-permission': ({**BACKGROUND_MV2, 'permissions': ['downloads', 'downloads.open']},
                          'self.started = true;', 'L3'),
    # Firefox's user_scripts, which Chromium doesn't have.
    'unknown-key': ({**BACKGROUND_MV2, 'user_scripts': {'api_script': 'background.js'}},
                    'self.started = true;', 'L1'),
    # A key that Firefox doesn't read either.
    'other-browser-key': ({**BACKGROUND_MV2, 'minimum_opera_version': '50'},
                          'self.started = true;', 'L3'),
    'missing-api': (BACKGROUND_MV2, 'browser.menus.onShown.addListener(() => {});', 'L1'),
    # Its background runs, then removes the add-on, as CTCT Extension does
    # without its enterprise's consent.
    'uninstalls-itself': ({**BACKGROUND_MV2, 'permissions': ['management']},
                          'setTimeout(() => chrome.management.uninstallSelf(), 1000);', 'L3'),
    # It scripts every open tab, as Dark Background and Light Text does, and
    # meets the runner's start tab, a browser page: Firefox refuses its own
    # pages too. It waits for the tab to load: before that, the tab has no
    # page to script, in Firefox either.
    'scripts-every-tab': ({**BACKGROUND_MV2, 'permissions': ['<all_urls>']}, '''
        (async () => {
            let tabs = [];
            while (!tabs.length) {
                await new Promise(resolve => setTimeout(resolve, 100));
                tabs = await browser.tabs.query({status: 'complete'});
            }
            for (const tab of tabs) {
                browser.tabs.executeScript(tab.id, {code: '1'});
            }
        })();''', 'L3'),
    'not-json': ('{"manifest_version": 2,', '', None),
    # Add-ons that load with --load-extension but whose .xpi doesn't
    # install: one without a Gecko ID (it has Firefox's other settings) or a
    # signature, and one whose icon isn't an image, which only the install
    # decodes.
    'no-gecko-id': ({**BACKGROUND_MV2, 'browser_specific_settings': {
        'gecko': {'strict_min_version': '109.0'}}}, 'self.started = true;', 'L0'),
    'broken-icon': ({**BACKGROUND_MV2, 'icons': {'48': 'icon.png'}}, 'self.started = true;',
                    'L0', {'icon.png': 'not a PNG'}),
    # The smoke check (L3): a popup, and content scripts on a site's page.
    'popup-shows': ({**BACKGROUND_MV2, **POPUP}, 'self.started = true;', 'L3',
                    {'popup.html': '<!doctype html><p>Popup</p>'}),
    'popup-throws': ({**BACKGROUND_MV2, **POPUP}, 'self.started = true;', 'L2',
                     {'popup.html': '<!doctype html><p>Popup</p><script src=popup.js></script>',
                      'popup.js': 'browser.notAnApi.call();'}),
    'popup-empty': ({**BACKGROUND_MV2, **POPUP}, 'self.started = true;', 'L2',
                    {'popup.html': '<!doctype html><body>'}),
    'content-runs': ({**BACKGROUND_MV2, **CONTENT}, 'self.started = true;', 'L3',
                     {'content.js': 'document.body.dataset.ran = location.host;'}),
    'content-throws': ({**BACKGROUND_MV2, **CONTENT}, 'self.started = true;', 'L2',
                       {'content.js': 'document.querySelector("#player").remove();'}),
    # Its content scripts never match the page made from its pattern.
    'content-excluded': ({**BACKGROUND_MV2, 'content_scripts': [
        {'matches': ['https://*.example.org/*'], 'exclude_matches': ['https://www.example.org/*'],
         'js': ['content.js']}]}, 'self.started = true;', 'L3', {'content.js': ''}),
}


class CorpusTest(unittest.TestCase):

    def test_levels(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            items, xpis = [], []
            for number, (name, (manifest, background, _, *files)) in enumerate(ADDONS.items()):
                xpi = folder / f'{name}.xpi'
                # Signed for its Gecko ID, as AMO signs an add-on.
                signer_id = f'{name}@corpus.test'
                if isinstance(manifest, dict):
                    manifest = {'browser_specific_settings': {'gecko': {'id': signer_id}},
                                **manifest}
                    signer_id = manifest['browser_specific_settings']['gecko'].get('id')
                    manifest = json.dumps(manifest)
                contents = {'manifest.json': manifest, 'background.js': background,
                            **(files[0] if files else {})}
                if signer_id:
                    contents = amo_signed(contents, signer_id)
                xpi.write_bytes(zipped(contents))
                items.append({'id': name, 'sha256': f'{number:064x}'})
                xpis.append(xpi)
            results = corpus.run_group(items, xpis, folder / 'unpacked',
                                       args=[signature_root_arg()])
        for name, (_, _, expected, *_) in ADDONS.items():
            with self.subTest(name):
                found, error = results[name]
                self.assertEqual(found, expected, error)
        self.assertIn('user_scripts', results['unknown-key'][1])
        self.assertIn('Uncaught', results['missing-api'][1])
        self.assertIn("reading 'call'", results['popup-throws'][1])
        self.assertEqual(results['popup-empty'][1], 'the popup shows nothing')
        self.assertIn("reading 'remove'", results['content-throws'][1])
        self.assertIn('because it appears to be corrupt', results['no-gecko-id'][1])
        self.assertIn("Could not decode image: 'icon.png'", results['broken-icon'][1])

    def test_content_url(self):
        for scripts, url in (
                ([{'matches': ['<all_urls>'], 'js': ['a.js']}], 'https://example.com/'),
                # The browser upgrades an http: page to https:.
                ([{'matches': ['http://*/*'], 'js': ['a.js']}], None),
                ([{'matches': ['*://*/*.md'], 'js': ['a.js']}], 'https://example.com/.md'),
                ([{'matches': ['*://*.youtube.com/watch*'], 'js': ['a.js']}],
                 'https://www.youtube.com/watch'),
                # CSS alone, the page's own world, exclusions and file: are
                # passed over.
                ([{'matches': ['<all_urls>'], 'css': ['a.css']},
                  {'matches': ['<all_urls>'], 'js': ['a.js'], 'world': 'MAIN'},
                  {'matches': ['<all_urls>'], 'js': ['a.js'], 'exclude_globs': ['*b*']},
                  {'matches': ['file:///*', 'https://mail.google.com/mail/*'], 'js': ['a.js']}],
                 'https://mail.google.com/mail/'),
                ([{'matches': ['https://*/*'], 'css': ['a.css']}], None)):
            with self.subTest(url):
                self.assertEqual(corpus.content_url({'content_scripts': scripts}), url)
