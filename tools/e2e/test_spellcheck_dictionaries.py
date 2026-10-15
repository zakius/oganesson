"""Spellcheck dictionaries download from Google's server while Helium's
services are off, as they are by default: Helium sends them to a placeholder
host then, where every request fails (oganesson/core/no-helium-services.patch).
--host-resolver-rules sends Google's dictionary host to a local HTTPS server,
which records the download.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import BrowserTest, Server, wait_for

DICTIONARY_HOST = 'redirector.gvt1.com'
DICTIONARY_PATH = '/edgedl/chrome/dict/'


class SpellcheckDictionariesTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-spellcheck-'))
        cert, key = cls.folder / 'cert.pem', cls.folder / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', f'/CN={DICTIONARY_HOST}',
                        '-addext', f'subjectAltName=DNS:{DICTIONARY_HOST}',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        # Any path answers 404: the test only needs the request.
        cls.server = Server({}, tls=(str(cert), str(key)))
        cls.browser_args = (
            f'--host-resolver-rules=MAP {DICTIONARY_HOST} 127.0.0.1:{cls.server.port}',
            '--ignore-certificate-errors')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def test_dictionary_downloads_from_google(self):
        wait_for(lambda: any(path.startswith(DICTIONARY_PATH) and path.endswith('.bdic')
                             for path in self.server.requests),
                 timeout=60, what="a dictionary download from Google's server")


if __name__ == '__main__':
    unittest.main()
