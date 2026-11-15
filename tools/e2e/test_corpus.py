"""The WebExtensions climb's corpus runner (corpus.py): small add-ons of each
kind it tells apart get the levels it gives them."""

import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import corpus

BACKGROUND_MV2 = {'manifest_version': 2, 'name': 'probe', 'version': '1',
                  'background': {'scripts': ['background.js']}}
KEY = ('MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDJnRbHexNTjRkPiiY/aArVJM+iKGwGLV6K7ivyrBfl1hwn8'
       'AjDF2aD2+1AsxJ2LeZL8z7FxJ7WPxJAoIyCfMOULQPV9LJ8Pq8egUMcC5YKvZN4rpIuEvLvWdAtwZlcFj6K2+'
       'Tlq8b5NE5Aj3BJwfRQVHtfdYj92BuW9zflWZPMDwIDAQAB')
# Chromium's ID for KEY: the first 32 hex digits of the key's SHA-256, as a to p.
KEYED_ID = ''.join(chr(ord('a') + int(digit, 16))
                   for digit in hashlib.sha256(base64.b64decode(KEY)).hexdigest()[:32])
# Each add-on: its manifest (text or JSON), background.js, and the level.
ADDONS = {
    'works': (BACKGROUND_MV2, 'self.started = true;', 'L2'),
    'firefox-metadata': ({**BACKGROUND_MV2, 'browser_specific_settings': {
        'gecko': {'id': 'probe@example.org'}}}, 'self.started = true;', 'L2'),
    # Its ID comes from the key, not from its folder.
    'keyed': ({**BACKGROUND_MV2, 'key': KEY}, 'self.started = true;', 'L2'),
    # Its error names the keyed add-on's page, which keeps that one at L2.
    'names-another': (BACKGROUND_MV2,
                      f"throw new Error('cannot reach chrome-extension://{KEYED_ID}/page.html');",
                      'L1'),
    # A dotted permission that Chromium has.
    'dotted-permission': ({**BACKGROUND_MV2, 'permissions': ['downloads', 'downloads.open']},
                          'self.started = true;', 'L2'),
    # Firefox's user_scripts, which Chromium doesn't have.
    'unknown-key': ({**BACKGROUND_MV2, 'user_scripts': {'api_script': 'background.js'}},
                    'self.started = true;', 'L1'),
    # A key that Firefox doesn't read either.
    'other-browser-key': ({**BACKGROUND_MV2, 'minimum_opera_version': '50'},
                          'self.started = true;', 'L2'),
    'missing-api': (BACKGROUND_MV2, 'browser.menus.onShown.addListener(() => {});', 'L1'),
    # Its background runs, then removes the add-on, as CTCT Extension does
    # without its enterprise's consent.
    'uninstalls-itself': ({**BACKGROUND_MV2, 'permissions': ['management']},
                          'setTimeout(() => chrome.management.uninstallSelf(), 1000);', 'L2'),
    'not-json': ('{"manifest_version": 2,', '', None),
}


class CorpusTest(unittest.TestCase):

    def test_levels(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            items, xpis = [], []
            for number, (name, (manifest, background, _)) in enumerate(ADDONS.items()):
                xpi = folder / f'{name}.xpi'
                with zipfile.ZipFile(xpi, 'w') as archive:
                    archive.writestr('manifest.json', manifest if isinstance(manifest, str)
                                     else json.dumps(manifest))
                    archive.writestr('background.js', background)
                items.append({'id': name, 'sha256': f'{number:064x}'})
                xpis.append(xpi)
            results = corpus.run_group(items, xpis, folder / 'unpacked')
        for name, (_, _, expected) in ADDONS.items():
            with self.subTest(name):
                found, error = results[name]
                self.assertEqual(found, expected, error)
        self.assertIn('user_scripts', results['unknown-key'][1])
        self.assertIn('Uncaught', results['missing-api'][1])
