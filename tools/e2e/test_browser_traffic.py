"""Browser traffic (oganesson/core/browser-traffic.patch, dubna's
components/browser_traffic): component update checks go direct to Google by
default, through the user's server when the rows are proxied, and nowhere
while a proxied row has no server: never back to Google, never to Helium.

--host-resolver-rules sends Google's update host to a local HTTPS server; the
user's server is plain HTTP on 127.0.0.1, which counts as localhost.
--component-updater=fast-update makes the first check come within seconds.
"""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from harness import BrowserTest, Server, wait_for

GOOGLE_HOST = 'update.googleapis.com'
GOOGLE_PATH = '/service/update2/json'
CRLSET = 'hfnkpimlhhgieaddgfemjhofmfblmnib'
PKI_METADATA = 'efniojlnjndmcbiieegkicadnoecjjef'
WIDEVINE = 'oimompecagnajdejgnnjijobebaeigek'
ROWS = ('certificates', 'drm', 'extensions', 'content_blocker', 'dictionaries')

# Every component is current.
NO_UPDATE = (")]}'\n" + json.dumps({'response': {'protocol': '4.0', 'apps': [
    {'appid': app, 'status': 'ok', 'updatecheck': {'status': 'noupdate'}}
    for app in (CRLSET, PKI_METADATA, WIDEVINE)]}})).encode()


def certificate(folder, host):
    cert, key = folder / 'cert.pem', folder / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', f'/CN={host}', '-addext', f'subjectAltName=DNS:{host}',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    return str(cert), str(key)


class TrafficTest(BrowserTest):
    """A Google stand-in and a user's server, both recording."""

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-traffic-'))
        reply = (200, {'Content-Type': 'application/json'}, NO_UPDATE)
        cls.google = Server({GOOGLE_PATH: reply}, tls=certificate(cls.folder, GOOGLE_HOST))
        cls.own = Server({'/com': reply, '/connectivitycheck': (204, {}, b'')})
        cls.browser_args = (
            f'--host-resolver-rules=MAP {GOOGLE_HOST} 127.0.0.1:{cls.google.port}',
            '--ignore-certificate-errors', '--component-updater=fast-update')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.google.stop()
        cls.own.stop()

    def restart_with(self, traffic):
        """Restarts the browser with Local State's browser_traffic prefs set."""
        self.browser.quit()
        path = self.browser.profile / 'Local State'
        state = json.loads(path.read_text())
        state['browser_traffic'] = traffic
        path.write_text(json.dumps(state))
        self.google.requests.clear()
        self.own.requests.clear()
        self.browser.start()

    def traffic_state(self):
        page = self.browser.new_tab('chrome://settings/updates')
        wait_for(lambda: page.eval("!!customElements.get('settings-browser-traffic-page')"),
                 what='the Browser traffic page')
        return page, page.eval(
            "import('chrome://resources/js/cr.js').then(cr => "
            "cr.sendWithPromise('getBrowserTraffic'))")


class DirectTest(TrafficTest):

    def test_components_check_google_directly(self):
        wait_for(lambda: any(CRLSET.encode() in body for body in self.google.posts),
                 timeout=120,
                 what="the certificate components' check at Google's update server")
        body = next(body for body in self.google.posts if CRLSET.encode() in body)
        # The Chrome Root Store and the CT log list come with the CRLSet, in
        # one check per row: Widevine's row is checked on its own.
        self.assertIn(PKI_METADATA.encode(), body)
        self.assertNotIn(WIDEVINE.encode(), body)
        self.assertEqual(self.own.requests, [])

        _, state = self.traffic_state()
        self.assertEqual(state['preset'], 'direct')
        wait_for(lambda: self.traffic_state()[1]['certificatesUpdated'] > time.time() * 1000 - 120000,
                 what='the certificate data recorded as current')

    def test_presets_set_the_rows(self):
        page, state = self.traffic_state()
        names = [row['name'] for row in state['rows']]
        self.assertEqual(names[:6], [*ROWS, 'bangs'])
        # Linux: browser updates are the package manager's.
        self.assertNotIn('browser_updates', names)
        self.assertEqual(state['browserUpdates'], 'packageManager')
        page.eval("chrome.send('applyBrowserTrafficPreset', ['shutIn'])")
        wait_for(lambda: self.traffic_state()[1]['preset'] == 'shutIn', what='Shut in')
        state = self.traffic_state()[1]
        self.assertFalse(any(row['automatic'] for row in state['rows']))
        self.assertFalse(state['healthPeriodic'])
        page.eval("chrome.send('setBrowserTrafficRow', ['certificates', true, false])")
        wait_for(lambda: self.traffic_state()[1]['preset'] == 'custom', what='Custom')
        page.eval("chrome.send('applyBrowserTrafficPreset', ['direct'])")
        wait_for(lambda: self.traffic_state()[1]['preset'] == 'direct', what='Direct')

    def test_server_must_be_https_or_local(self):
        page, _ = self.traffic_state()
        saved = page.eval("import('chrome://resources/js/cr.js').then(cr => "
                          "cr.sendWithPromise('setBrowserTrafficServer', 'http://example.org'))")
        self.assertFalse(saved)
        self.assertEqual(self.traffic_state()[1]['server'], '')
        answered = page.eval(
            "import('chrome://resources/js/cr.js').then(cr => "
            f"cr.sendWithPromise('testBrowserTrafficServer', 'http://127.0.0.1:{self.own.port}'))")
        self.assertTrue(answered)
        self.assertIn('/connectivitycheck', self.own.requests)


class ProxyTest(TrafficTest):

    def test_proxied_components_check_the_server_only(self):
        self.restart_with({
            'server': f'http://127.0.0.1:{self.own.port}/',
            **{row: {'route': 1} for row in ROWS}})
        wait_for(lambda: self.own.requests.count('/com') >= 2, timeout=120,
                 what="both component rows' checks at the user's server")
        self.assertEqual(self.google.requests, [])

    def test_proxied_rows_without_a_server_stay_idle(self):
        self.restart_with({row: {'route': 1} for row in ROWS})
        # fast-update checks within seconds; give it well past that.
        time.sleep(30)
        self.assertEqual(self.google.requests, [])
        self.assertEqual(self.own.requests, [])
        _, state = self.traffic_state()
        self.assertTrue(all(row['idle'] for row in state['rows'] if row['hasProxy']))
        self.assertTrue(state['needsServer'])


if __name__ == '__main__':
    unittest.main()
