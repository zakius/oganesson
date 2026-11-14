"""Push messages from closed sites, an opt-in (oganesson/core/push-opt-in.patch,
Settings > Browser traffic's settings-push-messages).

Helium's autopush driver delivers push messages through an autopush server.
Off, as in a fresh profile, a site's subscription fails and the browser opens
no connection to any push server. Turned on with the server left empty, it
goes to Mozilla's push server, never to Helium's: --host-resolver-rules sends
both hosts to a listener here, which notes the TLS server name each connection
asks for. With the test's fake autopush server set in Settings
(tools/fake_firefox_sync.py's PushServer), a site subscribes, its tab is
closed, and an encrypted message the fake pushes reaches its service worker,
which posts the text back to the site. Turned off, the connection closes.

Needs the `cryptography` package, like the fake.
"""

import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

from harness import BrowserTest, Server, wait_for
from test_firefox_sync import FIND

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from cryptography.hazmat.primitives.asymmetric import ec
    import fake_firefox_sync
    from fake_firefox_sync import b64url, ece_encrypt, public_bytes, unb64url
except ImportError as error:
    fake_firefox_sync = None
    MISSING = error.name

MOZILLA = 'push.services.mozilla.com'
HELIUM = 'push.helium.computer'
PREF = 'helium.services.web_push'
SERVER_PREF = 'helium.services.push_server'
ELEMENT = f"({FIND})('settings-push-messages')?.shadowRoot"
TOGGLE = f"{ELEMENT}?.querySelector('#pushMessages')"
SERVER = f"{ELEMENT}?.querySelector('#pushServer')"
# How long a browser that has no reason to connect gets to connect anyway.
QUIET = 5

PAGE = b'<title>push</title>'
# Shows the message, as a userVisibleOnly subscription must, and posts it to
# the site.
WORKER = b"""self.addEventListener('push', e => e.waitUntil(Promise.all([
  self.registration.showNotification('push', {body: e.data ? e.data.text() : ''}),
  fetch('/pushed', {method: 'POST', body: e.data ? e.data.text() : '(no data)'}),
])));"""
SUBSCRIBE = """(async () => {
  const registration = await navigator.serviceWorker.register('/sw.js');
  await navigator.serviceWorker.ready;
  try {
    const subscription = await registration.pushManager.subscribe(
        {userVisibleOnly: true, applicationServerKey: %s});
    return subscription.toJSON();
  } catch (e) {
    return {error: e.name};
  }
})()"""


class TlsListener:
    """Takes TCP connections and notes the server name (SNI) in each TLS
    ClientHello, then hangs up."""

    def __init__(self):
        self.names = []
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                try:
                    hello = conn.recv(4096)
                except OSError:
                    hello = b''
            self.names.append(next((name for name in (MOZILLA, HELIUM)
                                    if name.encode() in hello), repr(hello[:16])))

    def stop(self):
        self.sock.close()


class PushMessagesTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        if not fake_firefox_sync:
            raise unittest.SkipTest(f'the fake push server needs {MISSING}')
        cls.push = fake_firefox_sync.PushServer()
        threading.Thread(target=cls.push.serve_forever, daemon=True).start()
        cls.tls = TlsListener()
        cls.site = Server({'/': (200, {'Content-Type': 'text/html'}, PAGE),
                           '/sw.js': (200, {'Content-Type': 'text/javascript'}, WORKER),
                           '/pushed': (200, {}, b'')})
        cls.browser_args = (f'--host-resolver-rules=MAP {MOZILLA} 127.0.0.1:{cls.tls.port},'
                            f'MAP {HELIUM} 127.0.0.1:{cls.tls.port}',)
        # The site may show notifications, as a user would allow. A DevTools
        # permission override would end with the session that set it.
        site = cls.site.url('').rstrip('/') + ',*'
        cls.prefs = {'profile': {'content_settings': {'exceptions': {
            'notifications': {site: {'setting': 1}}}}}}
        super().setUpClass()
        cls.key = b64url(public_bytes(ec.generate_private_key(ec.SECP256R1())))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.site.stop()
        cls.tls.stop()
        cls.push.shutdown()

    def subscribe(self):
        """The site's subscription, as toJSON() gives it, or {'error': name}.
        The tab is closed again."""
        page = self.browser.new_tab(self.site.url('/'))
        try:
            wait_for(lambda: page.eval('document.title') == 'push', what='the page')
            return page.eval(SUBSCRIBE % json.dumps(self.key))
        finally:
            self.browser.close_target(page)

    def settings(self):
        page = self.browser.new_tab('chrome://settings/updates')
        wait_for(lambda: page.eval(f'!!{TOGGLE}'), what='the switch')
        return page

    def pref(self, page, name):
        return page.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)}).then(p => p.value)')

    def set_server(self, page, value):
        page.eval(f'(() => {{ const input = {SERVER}; input.value = {json.dumps(value)};'
                  " input.dispatchEvent(new CustomEvent('change')); })()")

    def test_off_mozilla_own_server_off(self):
        # Off: subscribing fails, and nothing connects.
        self.assertIn('error', self.subscribe())
        time.sleep(QUIET)
        self.assertEqual(self.tls.names, [])
        self.assertEqual(self.push.connections_made, 0)

        settings = self.settings()
        self.assertEqual(settings.eval(f'{TOGGLE}.label'), 'Push messages from closed sites')
        self.assertIs(settings.eval(f'{TOGGLE}.checked'), False)
        self.assertIs(settings.eval(f'{ELEMENT}.querySelector("#serverRow").hidden'), True)
        settings.eval(f'{TOGGLE}.click()')
        wait_for(lambda: self.pref(settings, PREF) is True, what='the pref')
        self.assertIs(settings.eval(f'{ELEMENT}.querySelector("#serverRow").hidden'), False)

        # On with no server: Mozilla's, which the listener stands in for.
        # The TLS handshake fails there, so the subscription does too.
        self.assertIn('error', self.subscribe())
        wait_for(lambda: self.tls.names, what="a connection to Mozilla's push server")
        self.assertEqual(set(self.tls.names), {MOZILLA})

        # A server the browser wouldn't use isn't saved.
        self.set_server(settings, 'ws://example.com/')
        self.assertIs(settings.eval(f'{SERVER}.invalid'), True)
        self.assertEqual(self.pref(settings, SERVER_PREF), '')
        self.set_server(settings, self.push.url)
        self.assertIs(settings.eval(f'{SERVER}.invalid'), False)
        wait_for(lambda: self.pref(settings, SERVER_PREF) == self.push.url,
                 what='the server pref')

        subscription = self.subscribe()
        self.assertIn('endpoint', subscription, subscription)
        channel = subscription['endpoint'].rsplit('/', 1)[-1]
        # The site's tab is closed: the message wakes its service worker.
        keys = subscription['keys']
        message = ece_encrypt(unb64url(keys['p256dh']), unb64url(keys['auth']),
                              b'hello from the push server')
        self.push.notify(channel, message)
        wait_for(lambda: b'hello from the push server' in self.site.posts, timeout=30,
                 what="the message at the site's service worker")
        wait_for(lambda: self.push.acks, what='the message acknowledged')

        # Off again: the connection closes.
        settings.eval(f'{TOGGLE}.click()')
        wait_for(lambda: self.pref(settings, PREF) is False, what='the pref off')
        wait_for(lambda: not self.push.connections, what='the push connection to close')
        self.browser.close_target(settings)


if __name__ == '__main__':
    unittest.main()
