"""Chrome Web Store extensions update from Google's own update server while
Helium's services are off, as they are by default: Helium sends them to a
placeholder host then, where every request fails
(oganesson/core/no-helium-services.patch).

--host-resolver-rules sends Google's update host to a local HTTPS server. A
small extension whose manifest names the store's update URL is packed with
the browser's --pack-extension, and a file in the profile's External
Extensions folder has the browser install it from that server. Then an update
check for the installed extension has to reach the server too.
"""

import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import BINARY, BrowserTest, Server, wait_for

UPDATE_HOST = 'clients2.google.com'
UPDATE_PATH = '/service/update2/crx'
CRX_PATH = '/test-extension.crx'


def extension_id(key):
    """An extension's ID: the first 16 bytes of its public key's SHA-256, in a-p."""
    der = subprocess.run(['openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER'],
                         check=True, capture_output=True).stdout
    return ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])


class WebstoreUpdatesTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-webstore-'))
        cert, key = cls.folder / 'cert.pem', cls.folder / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', f'/CN={UPDATE_HOST}', '-addext', f'subjectAltName=DNS:{UPDATE_HOST}',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        ext, ext_key = cls.folder / 'ext', cls.folder / 'ext-key.pem'
        ext.mkdir()
        (ext / 'manifest.json').write_text(json.dumps({
            'name': 'Store update test', 'version': '1.0', 'manifest_version': 3,
            'update_url': f'https://{UPDATE_HOST}{UPDATE_PATH}'}))
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-out', str(ext_key)], check=True,
                       capture_output=True)
        subprocess.run([str(BINARY), f'--pack-extension={ext}', f'--pack-extension-key={ext_key}',
                        '--no-message-box', f'--user-data-dir={cls.folder / "pack-profile"}'],
                       check=True, capture_output=True, timeout=60)
        cls.id = extension_id(ext_key)
        crx = (cls.folder / 'ext.crx').read_bytes()
        update = (f'<?xml version="1.0" encoding="UTF-8"?>'
                  f'<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">'
                  f'<app appid="{cls.id}" status="ok"><updatecheck status="ok" version="1.0" '
                  f'codebase="https://{UPDATE_HOST}{CRX_PATH}" '
                  f'hash_sha256="{hashlib.sha256(crx).hexdigest()}"/></app></gupdate>').encode()
        cls.server = Server({UPDATE_PATH: (200, {'Content-Type': 'text/xml'}, update),
                             CRX_PATH: (200, {'Content-Type': 'application/x-chrome-extension'},
                                        crx)},
                            tls=(str(cert), str(key)))
        cls.browser_args = (f'--host-resolver-rules=MAP {UPDATE_HOST} 127.0.0.1:{cls.server.port}',
                            '--ignore-certificate-errors')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def test_installed_store_extension_updates_from_google(self):
        self.browser.quit()
        folder = self.browser.profile / 'External Extensions'
        folder.mkdir(exist_ok=True)
        (folder / f'{self.id}.json').write_text(json.dumps(
            {'external_update_url': f'https://{UPDATE_HOST}{UPDATE_PATH}'}))
        self.browser.start()
        wait_for(lambda: (self.browser.profile / 'Default/Extensions' / self.id).is_dir(),
                 timeout=60, what='the extension installed from the update server')
        checks = self.server.requests.count(UPDATE_PATH)
        # The Update button on chrome://extensions.
        page = self.browser.new_tab('chrome://extensions')
        wait_for(lambda: page.eval('typeof chrome.developerPrivate') == 'object',
                 what='chrome://extensions')
        page.eval('chrome.developerPrivate.autoUpdate()')
        wait_for(lambda: self.server.requests.count(UPDATE_PATH) > checks, timeout=30,
                 what="the installed extension's update check at Google's update server")


if __name__ == '__main__':
    unittest.main()
