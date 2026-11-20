"""A prerendered page's cross-origin iframes wait until it is opened
(dubna/patches/prerender-cross-origin-frames.patch).

A page that sends `Supports-Loading-Mode: prerender-cross-origin-frames` may
have its cross-origin iframes load while it is prerendered when the page that
prerenders it is in the Prerender2CrossOriginIframes origin trial (Chromium
158), or for every site (Chromium 159's default). Here only chrome://flags
turns it on (the test's --enable-features).

The start page is in the trial with a token signed by the test's own key
(--origin-trial-public-key) and prerenders /next, which embeds an iframe from
another origin. The test opens it through the browser's DevTools target,
without attaching to the page: an attached session turns prerendering off.
Helium's uBO turns preloading off, so the test turns its "Disable
pre-fetching" off first.
"""

import base64
import json
import struct
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from harness import BrowserTest, Server, wait_for

KEY = Ed25519PrivateKey.generate()
PUBLIC_KEY = KEY.public_key().public_bytes(serialization.Encoding.Raw,
                                           serialization.PublicFormat.Raw)
# How long a prerendered page gets to load its iframe.
QUIET = 5


def trial_token(origin):
    """An origin trial token for `origin`, signed by KEY (the format of
    Chromium's tools/origin_trials/generate_token.py, version 3)."""
    payload = json.dumps({'origin': origin, 'feature': 'Prerender2CrossOriginIframes',
                          'expiry': int(time.time()) + 3600}).encode()
    version = bytes([3])
    length = struct.pack('>I', len(payload))
    signature = KEY.sign(version + length + payload)
    return base64.b64encode(version + signature + length + payload).decode()


class PrerenderTest(BrowserTest):
    browser_args = [f'--origin-trial-public-key={base64.b64encode(PUBLIC_KEY).decode()}']
    prefs = {'net': {'network_prediction_options': 0}}
    wait_ubo = True
    # Whether the iframe loads before the page is opened.
    frame_loads_early = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ubo = cls.browser.ubo_background()
        ubo.eval("µBlock.changeUserSettings('prefetchingDisabled', false)")
        ubo.close()

    def test_cross_origin_iframe_waits_for_the_page_to_open(self):
        frames = Server({'/frame': (200, {'Content-Type': 'text/html'}, b'frame')})
        pages = Server({})
        self.addCleanup(frames.stop)
        self.addCleanup(pages.stop)
        token = trial_token(f'http://127.0.0.1:{pages.port}')
        rules = '{"prerender": [{"source": "list", "urls": ["/next"], "eagerness": "immediate"}]}'
        pages.routes['/'] = (200, {'Content-Type': 'text/html', 'Origin-Trial': token},
                             f'<script type="speculationrules">{rules}</script>'.encode())
        frame = frames.url('/frame', host='localhost')
        pages.routes['/next'] = (200, {'Content-Type': 'text/html',
                                       'Supports-Loading-Mode': 'prerender-cross-origin-frames'},
                                 f'<iframe src="{frame}"></iframe>'.encode())

        self.browser.browser_call('Target.createTarget', url=pages.url('/'))
        wait_for(lambda: '/next' in pages.requests, what='the prerender of /next')
        self.assertEqual(pages.headers['/next'].get('Sec-Purpose'), 'prefetch;prerender')
        if self.frame_loads_early:
            wait_for(lambda: frames.requests, timeout=QUIET, what='the prerendered iframe')
        else:
            time.sleep(QUIET)
            self.assertEqual(frames.requests, [])
        # The start page is in the trial: its token is valid. A second tab,
        # since attaching to the first would have ended its prerender.
        start = pages.url('/')
        tab = self.browser.new_tab(start)
        self.addCleanup(self.browser.close_target, tab)
        # Not the tab's first document, about:blank, which is complete too.
        loaded = f'location.href === {json.dumps(start)} && document.readyState === "complete"'
        wait_for(lambda: tab.eval(loaded, gesture=False), what='the start page in a second tab')
        frame_id = tab.call('Page.getFrameTree')['frameTree']['frame']['id']
        trials = tab.call('Page.getOriginTrials', frameId=frame_id)['originTrials']
        statuses = [token['status'] for trial in trials
                    if trial['trialName'] == 'Prerender2CrossOriginIframes'
                    for token in trial['tokensWithStatus']]
        self.assertEqual(statuses, ['Success'])


class PrerenderFlagTest(PrerenderTest):
    """chrome://flags' "Prerender2CrossOriginIframes" still lets the iframe
    load early, which also shows that the test sees an early load."""
    browser_args = PrerenderTest.browser_args + ['--enable-features=Prerender2CrossOriginIframes']
    frame_loads_early = True


if __name__ == '__main__':
    unittest.main()
