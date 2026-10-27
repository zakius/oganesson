"""Requests across a restart of Helium's uBlock Origin. On a new
profile's first launch uBlock restarts itself (`runtime.reload()`). Requests
in flight keep their way to the network through the restart: a navigation the
browser restarts for a `Critical-CH` client hint, as Google's pages ask, loads
instead of leaving its tab blank, and a page loading images doesn't lose one.
Test 1 holds the navigation with uBlock's own suspension,
`vAPI.net.suspend()`, so it is in flight when uBlock restarts. Until uBlock
filters, it holds requests with a pending promise, as in Firefox: a page
opened while it loads its lists gets its image and audio, and not the image a
filter blocks. An add-on whose reload fails, the only one with webRequest,
gets the requests of a page opened meanwhile once it loads again.
"""

import base64
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from harness import UBO, BrowserTest, Server, wait_for

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
                       '2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
HTML = {'Content-Type': 'text/html'}
HINT = 'Sec-CH-UA-Platform-Version'


def silence():
    """A tenth of a second of silence, as a WAV file."""
    data = io.BytesIO()
    with wave.open(data, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b'\0\0' * 800)
    return data.getvalue()


def hinted(headers):
    """Asks for a client hint the browser sends only on request: the browser
    restarts the navigation with it."""
    if headers.get(HINT) is None:
        return 200, {**HTML, 'Accept-CH': HINT, 'Critical-CH': HINT}, b'<title>no hint</title>'
    return 200, HTML, b'<title>hinted</title>'


PAGE = (b'<!doctype html><title>page</title><img id=allowed src="/allowed.png">'
        b'<img id=blocked src="/blocked.png"><audio id=audio preload=auto src="/audio.wav"></audio>')
# Images every 5 ms, counted as they load or fail.
BURST = ("window.counts = {sent: 0, loaded: 0, failed: 0};"
         " window.burst = setInterval(() => { const image = new Image();"
         " image.onload = () => counts.loaded++; image.onerror = () => counts.failed++;"
         " image.src = '/allowed.png?' + counts.sent++; }, 5)")


class UboRestartTest(BrowserTest):
    """Steps run in order and build on each other."""

    wait_ubo = True

    @classmethod
    def setUpClass(cls):
        cls.server = Server({
            '/hinted': hinted,
            '/page': (200, HTML, PAGE),
            '/empty': (200, HTML, b'<!doctype html><title>empty</title>'),
            '/allowed.png': (200, {'Content-Type': 'image/png'}, PNG),
            '/blocked.png': (200, {'Content-Type': 'image/png'}, PNG),
            '/audio.wav': (200, {'Content-Type': 'audio/wav'}, silence()),
        })
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def restart_ubo(self, hold=None, starting=None):
        """Restarts uBlock, as on a first launch, and waits until it filters
        again. With `hold`, uBlock holds the requests `hold()` sends until it
        restarts. `starting()` runs once the new uBlock listens for requests,
        before it filters."""
        ubo = self.browser.ubo_background()
        try:
            started = ubo.eval('performance.timeOrigin')
            if hold:
                ubo.eval('vAPI.net.suspend()')
                hold()
                wait_for(lambda: ubo.eval('vAPI.net.pendingRequests.length'),
                         what='uBlock Origin holding the request')
            ubo.eval('setTimeout(() => chrome.runtime.reload(), 0)')
        finally:
            ubo.close()

        def new_ubo(check):
            """`check` on the restarted uBlock's background page. Its target
            keeps the URL across the restart, so each try attaches anew."""
            page = None
            try:
                page = self.browser.page(f'chrome-extension://{UBO}/background.html')
                return page.eval(f'performance.timeOrigin != {started} && ({check})')
            except (OSError, RuntimeError, ConnectionError):
                return False
            finally:
                if page:
                    page.close()
        if starting:
            wait_for(lambda: new_ubo('self.vAPI?.net !== undefined'), timeout=60,
                     what='the restarted uBlock Origin to listen')
            starting()
        wait_for(lambda: new_ubo('self.µBlock?.readyToFilter'), timeout=60,
                 what='uBlock Origin to restart')

    def test_1_navigation_in_flight_loads(self):
        url = self.server.url('/hinted')
        self.restart_ubo(hold=lambda: self.browser.new_tab(url).close())
        wait_for(lambda: any(t['url'] == url and t['title'] == 'hinted'
                             for t in self.browser.targets()),
                 timeout=30, what='the navigation to load with the hint')

    def test_2_images_in_flight_load(self):
        page = self.browser.new_tab(self.server.url('/empty'))
        try:
            wait_for(lambda: page.eval('document.title') == 'empty', what='the page')
            page.eval(BURST)
            self.restart_ubo()
            page.eval('clearInterval(burst)')
            wait_for(lambda: page.eval('counts.loaded + counts.failed == counts.sent'),
                     timeout=30, what='every image to load or fail')
            counts = page.eval('counts')
        finally:
            page.close()
        self.assertEqual(counts['failed'], 0, counts)

    def test_3_page_opened_while_ubo_starts_is_filtered_and_complete(self):
        ubo = self.browser.ubo_background()
        try:
            ubo.eval("µBlock.appendUserFilters('/blocked.png$image')")
        finally:
            ubo.close()
        self.server.requests.clear()
        pages = []
        self.restart_ubo(starting=lambda: pages.append(self.browser.new_tab(self.server.url('/page'))))
        try:
            # The tab is on about:blank until uBlock lets the navigation go.
            wait_for(lambda: pages[0].eval('document.getElementById("allowed")?.naturalWidth == 1'
                                           ' && document.getElementById("audio")?.readyState == 4'),
                     timeout=30, what="the page's image and audio")
        finally:
            pages[0].close()
        self.assertIn('/allowed.png', self.server.requests)
        self.assertIn('/audio.wav', self.server.requests)
        self.assertNotIn('/blocked.png', self.server.requests)


BLOCKER = {
    'manifest_version': 2,
    'name': 'Blocker',
    'version': '1',
    'permissions': ['webRequest', 'webRequestBlocking', '<all_urls>'],
    'background': {'scripts': ['background.js']},
}


class FailedReloadTest(BrowserTest):
    """With uBlock disabled, a test add-on is the only one with webRequest."""

    prefs = {'extensions': {'settings': {UBO: {'disable_reasons': [1]}}}}

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-ubo-restart-'))
        (cls.folder / 'manifest.json').write_text(json.dumps(BLOCKER))
        (cls.folder / 'background.js').write_text(
            "chrome.webRequest.onBeforeRequest.addListener(() => ({cancel: true}),"
            " {urls: ['*://*/probe']}, ['blocking']);")
        cls.server = Server({'/empty': (200, HTML, b'<!doctype html><title>empty</title>'),
                             '/probe': (200, HTML, b'probe')})
        cls.browser_args = (f'--load-extension={cls.folder}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def background(self):
        return next((t for t in self.browser.targets()
                     if t['url'].endswith('/_generated_background_page.html')), None)

    def test_page_opened_during_a_failed_reload_reaches_the_reloaded_add_on(self):
        extension = wait_for(self.background, what='the add-on')['url'].split('/')[2]
        extensions = self.browser.new_tab('chrome://extensions')
        page = None
        try:
            wait_for(lambda: extensions.eval('typeof chrome.developerPrivate') == 'object',
                     what='chrome://extensions')
            # An unpacked add-on loads again only in developer mode.
            extensions.eval('chrome.developerPrivate.updateProfileConfiguration({inDeveloperMode: true})')
            reload = f"chrome.developerPrivate.reload('{extension}', {{failQuietly: true}})"
            (self.folder / 'manifest.json').write_text('{')
            extensions.eval(reload)
            wait_for(lambda: not self.background(), what='the add-on to unload')
            page = self.browser.new_tab(self.server.url('/empty'))
            wait_for(lambda: page.eval('document.title') == 'empty', what='the page')
            (self.folder / 'manifest.json').write_text(json.dumps(BLOCKER))
            # A reload before the failed one has finished is refused: retry only
            # then, as one that succeeded and ran again would unload it again.
            wait_for(lambda: extensions.eval(f'{reload}.then(() => true, () => false)'),
                     what='a reload to start')
            wait_for(self.background, what='the add-on to load again')
            # Its listener registers a moment after its background page starts.
            wait_for(lambda: page.eval("fetch('/probe').then(() => false, () => true)"),
                     timeout=10, what="the add-on to block the page's request")
        finally:
            extensions.close()
            if page:
                page.close()

if __name__ == '__main__':
    unittest.main()
