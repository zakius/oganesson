"""The Autoplay site setting (docs/autoplay.md).

Pages on a local server play a short WAV file (written here with the
stdlib wave module) in a <video>. A page that autoplays has the autoplay
attribute and calls play() whenever it is visible, as video sites do; it
records each play() result in `results`. Script runs without a user
gesture (`gesture=False`), so only the input the test sends counts.

Block audio and video (the default): nothing plays on load, in a tab opened
by middle-clicking a same-origin link once that tab is activated, after a
same-tab link click, or muted, also when an extension relays the click that
opened the tab and injects script into it, as uBlock Origin does on YouTube.
A click or a key press in the page lets
play() start, also after a same-document (SPA) navigation once the click's
transient activation has expired. Block audio is Chromium's policy: muted
plays, sound doesn't. Allow audio and video plays. An allow exception for
one site overrides the default. The settings page's three choices set the
default.
"""

import io
import json
import shutil
import tempfile
import time
import unittest
import wave
from pathlib import Path

from harness import BrowserTest, Page, Server, wait_for
from test_firefox_sync import FIND

ALLOW, BLOCK, ASK = 1, 2, 3  # ContentSetting values in Preferences


def silence(seconds=10):
    data = io.BytesIO()
    with wave.open(data, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b'\0\0' * 8000 * seconds)
    return data.getvalue()


# A block above the video to click on, away from the video's controls.
PAGE = """<!doctype html><title>{title}</title>
<div id="pad" style="height: 120px">{body}</div>
<video id="v" src="/silence.wav" controls {attrs}></video>
<script>
window.results = [];
window.attempt = () => v.play().then(() => results.push('played'),
                                     e => results.push(e.name));
{script}
</script>"""
AUTOPLAY = """
if (document.visibilityState === 'visible') attempt();
document.addEventListener('visibilitychange',
    () => document.visibilityState === 'visible' && attempt());
window.audioState = () => audio.state;
const audio = new AudioContext();"""
# Same-document navigation as on YouTube: the click only changes the URL; the
# page starts a new video later, once the click's transient activation is gone.
SPA = """
pad.onclick = () => history.pushState({}, '', '/spa.html?v=next');
window.playNew = () => {
  const video = document.createElement('video');
  video.src = '/silence.wav';
  document.body.append(video);
  return video.play().then(() => 'played', e => e.name);
};"""


def page(title, attrs='', script='', body=''):
    html = PAGE.format(title=title, attrs=attrs, script=script, body=body)
    return 200, {'Content-Type': 'text/html'}, html.encode()


ROUTES = {
    '/silence.wav': (200, {'Content-Type': 'audio/wav'}, silence()),
    '/autoplay.html': page('autoplay', 'autoplay', AUTOPLAY),
    '/muted.html': page('muted', 'autoplay muted', AUTOPLAY),
    '/idle.html': page('idle'),
    '/link.html': page('link', body='<a id="link" href="/autoplay.html">next</a>'),
    '/spa.html': page('spa', script=SPA),
}


class AutoplayTest(BrowserTest):
    """A browser with the Autoplay setting given by `setting` (None: the
    default) and `exceptions` (pattern: setting)."""

    setting = None
    exceptions = {}
    # The harness's wait for uBlock Origin evaluates script in its background
    # page with a user gesture, which its messages then pass on to new pages,
    # and that mustn't count as input there.
    wait_ubo = True
    # A fake audio output: opening the machine's ALSA device can stall
    # playback, and the load event with it.
    browser_args = ('--disable-audio-output',)

    @classmethod
    def setUpClass(cls):
        cls.server = Server(ROUTES)
        content = {}
        if cls.setting:
            content['default_content_setting_values'] = {'autoplay': cls.setting}
        if cls.exceptions:
            content['content_settings'] = {'exceptions': {'autoplay': {
                f'{pattern},*': {'setting': value} for pattern, value in cls.exceptions.items()}}}
        cls.prefs = {'profile': content}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def open(self, path, host='127.0.0.1'):
        url = self.server.url(path, host)
        page = self.browser.new_tab(url)
        self.wait_loaded(page, url)
        return page

    def wait_loaded(self, page, url):
        # Not the initial about:blank, also complete.
        wait_for(lambda: page.eval(f"location.href === {json.dumps(url)}"
                                   " && document.readyState === 'complete'", gesture=False),
                 what=url)

    def results(self, page):
        return page.eval('results', gesture=False)

    def paused(self, page):
        return page.eval('v.paused', gesture=False)

    def assert_plays(self, page):
        wait_for(lambda: self.results(page), what='a play() result')
        self.assertEqual(self.results(page)[0], 'played')
        self.assertFalse(self.paused(page))

    def assert_blocked(self, page):
        wait_for(lambda: self.results(page), what='a play() result')
        # An allowed autoplay starts as the media gets enough data.
        wait_for(lambda: page.eval('v.readyState === HTMLMediaElement.HAVE_ENOUGH_DATA',
                                   gesture=False), what='the media to load')
        self.assertNotIn('played', self.results(page))
        self.assertIn('NotAllowedError', self.results(page))
        self.assertTrue(self.paused(page))

    def try_play(self, page):
        return page.eval('v.play().then(() => "played", e => e.name)', gesture=False)

    def click(self, page, selector='#pad'):
        """A trusted click in the page, as Page.click without its gesture."""
        x, y = page.eval(f'(() => {{ const r = document.querySelector({json.dumps(selector)})'
                         '.getBoundingClientRect(); return [r.x + 10, r.y + 10]; })()',
                         gesture=False)
        for kind in ('mousePressed', 'mouseReleased'):
            page.call('Input.dispatchMouseEvent', type=kind, x=x, y=y, button='left',
                      clickCount=1)

    def press_key(self, page):
        for kind in ('keyDown', 'keyUp'):
            page.call('Input.dispatchKeyEvent', type=kind, key='a', code='KeyA', text='a',
                      windowsVirtualKeyCode=65)


class BlockAudioAndVideoTest(AutoplayTest):
    """The default."""

    def test_autoplay_on_load_blocked(self):
        page = self.open('/autoplay.html')
        self.assert_blocked(page)
        # Web Audio follows the same rule.
        self.assertEqual(page.eval('audioState()', gesture=False), 'suspended')

    def test_middle_clicked_link_stays_paused_when_activated(self):
        opener = self.open('/link.html')
        before = {t['id'] for t in self.browser.targets()}
        self.browser.click_element(opener, '#link', button=2)
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['id'] not in before
                                        and t['url'].endswith('/autoplay.html')), None),
                          what='the background tab')
        page = Page(target)
        self.wait_loaded(page, self.server.url('/autoplay.html'))
        self.assertEqual(page.eval('document.visibilityState', gesture=False), 'hidden')
        self.browser._get(f'/json/activate/{target["id"]}')
        wait_for(lambda: page.eval('document.visibilityState', gesture=False) == 'visible',
                 what='the tab to show')
        self.assert_blocked(page)

    def test_same_tab_link_click_blocked(self):
        page = self.open('/link.html')
        self.click(page, '#link')
        self.wait_loaded(page, self.server.url('/autoplay.html'))
        self.assert_blocked(page)
        self.assertEqual(page.eval('audioState()', gesture=False), 'suspended')

    def test_muted_autoplay_blocked(self):
        page = self.open('/muted.html')
        self.assert_blocked(page)

    def test_click_in_page_allows_play(self):
        page = self.open('/idle.html')
        self.assertEqual(self.try_play(page), 'NotAllowedError')
        self.click(page)
        self.assertEqual(self.try_play(page), 'played')

    def test_key_press_in_page_allows_play(self):
        page = self.open('/idle.html')
        self.assertEqual(self.try_play(page), 'NotAllowedError')
        self.press_key(page)
        self.assertEqual(self.try_play(page), 'played')

    def test_click_then_spa_navigation_plays(self):
        page = self.open('/spa.html')
        self.assertEqual(page.eval('playNew()', gesture=False), 'NotAllowedError')
        self.click(page)
        self.assertTrue(page.eval('location.search', gesture=False), 'the URL changed')
        # Past the 5 s of transient activation: only the document's sticky
        # activation is left.
        time.sleep(6)
        self.assertFalse(page.eval('navigator.userActivation.isActive', gesture=False))
        self.assertEqual(page.eval('playNew()', gesture=False), 'played')

    def default(self, page):
        return page.eval("import('chrome://resources/js/cr.js').then(cr => cr.sendWithPromise("
                         "'getDefaultValueForContentType', 'autoplay')).then(v => v.setting)")

    def test_site_settings_row(self):
        page = self.browser.new_tab('chrome://settings/content')
        # The row in whichever of the page's lists has it.
        row = (f"(({FIND})('settings-site-settings-page')?.shadowRoot"
               "?.querySelectorAll('settings-site-settings-list') ?? []).values()"
               ".map(list => list.shadowRoot?.querySelector('#autoplay')).find(Boolean)")
        wait_for(lambda: page.eval(f'!!{row}'), what='the Autoplay row')
        wait_for(lambda: 'Block audio and video' in page.eval(f'{row}.subLabel || ""'),
                 what='the default in the row')

    def test_three_choices(self):
        page = self.browser.new_tab('chrome://settings/content/autoplay')
        group = f"({FIND})('settings-category-default-radio-group')"
        wait_for(lambda: page.eval(f'!!{group}?.shadowRoot'), what='the choices')
        wait_for(lambda: page.eval(f"{group}.shadowRoot.querySelector('#blockRadioOption')"
                                   '.checked'), what='Block audio and video selected')
        self.assertEqual(self.default(page), 'block')

        def block_again():
            # The class's other tests run with the default.
            page.eval(f"{group}.shadowRoot.querySelector('#blockRadioOption').click()")
            wait_for(lambda: self.default(page) == 'block', what='block again')
        self.addCleanup(block_again)
        for option, value in (('allowRadioOption', 'allow'), ('askRadioOption', 'ask'),
                              ('blockRadioOption', 'block'), ('allowRadioOption', 'allow')):
            page.eval(f"{group}.shadowRoot.querySelector('#{option}').click()")
            wait_for(lambda: self.default(page) == value, what=value)
        # The choice applies to the next page loaded.
        self.assert_plays(self.open('/autoplay.html'))


class ExtensionScriptTest(AutoplayTest):
    """An extension that passes the middle-click opening a tab on to the tab:
    its content script tells its background page, which holds the click's
    activation for 5 s and injects script into the new tab as it loads, as
    uBlock Origin does with its scriptlets. That script runs with the
    activation, which isn't input in the page."""

    MANIFEST = {
        'manifest_version': 2,
        'name': 'Autoplay test relay',
        'version': '1',
        'permissions': ['tabs', 'http://127.0.0.1/*'],
        'background': {'scripts': ['background.js']},
        'content_scripts': [{'matches': ['http://127.0.0.1/link.html'], 'js': ['content.js']}],
    }
    BACKGROUND = """
    let injected = 0;
    chrome.runtime.onMessage.addListener(() => {});
    chrome.tabs.onUpdated.addListener((id, change, tab) => {
      if (change.status === 'loading' && (tab.url || '').endsWith('/autoplay.html')) {
        chrome.tabs.executeScript(id, {code: '0', runAt: 'document_start'}, () => {
          injected += !chrome.runtime.lastError;
        });
      }
    });
    """
    CONTENT = "addEventListener('mousedown', () => chrome.runtime.sendMessage('click'), true);"

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-autoplay-'))
        (cls.folder / 'manifest.json').write_text(json.dumps(cls.MANIFEST))
        (cls.folder / 'background.js').write_text(cls.BACKGROUND)
        (cls.folder / 'content.js').write_text(cls.CONTENT)
        cls.browser_args = (*AutoplayTest.browser_args, f'--load-extension={cls.folder}')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_injected_script_doesnt_unblock(self):
        opener = self.open('/link.html')
        before = {t['id'] for t in self.browser.targets()}
        self.browser.click_element(opener, '#link', button=2)
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['id'] not in before
                                        and t['url'].endswith('/autoplay.html')), None),
                          what='the background tab')
        page = Page(target)
        self.wait_loaded(page, self.server.url('/autoplay.html'))
        # The scenario: the script went in, and the click's activation with it.
        background = self.browser.page('_generated_background_page.html')
        wait_for(lambda: background.eval('injected', gesture=False), what='the injected script')
        self.assertTrue(page.eval('navigator.userActivation.hasBeenActive', gesture=False))
        self.browser._get(f'/json/activate/{target["id"]}')
        wait_for(lambda: page.eval('document.visibilityState', gesture=False) == 'visible',
                 what='the tab to show')
        self.assert_blocked(page)


class BlockAudioTest(AutoplayTest):
    setting = ASK

    def test_unmuted_autoplay_blocked(self):
        self.assert_blocked(self.open('/autoplay.html'))

    def test_muted_autoplay_plays(self):
        self.assert_plays(self.open('/muted.html'))


class AllowTest(AutoplayTest):
    setting = ALLOW

    def test_autoplay_plays(self):
        page = self.open('/autoplay.html')
        self.assert_plays(page)
        self.assertEqual(page.eval('audioState()', gesture=False), 'running')


class ExceptionTest(AutoplayTest):
    exceptions = {'[*.]localhost': ALLOW}

    def test_allowed_site_plays(self):
        self.assert_plays(self.open('/autoplay.html', host='localhost'))

    def test_other_site_blocked(self):
        self.assert_blocked(self.open('/autoplay.html'))


if __name__ == '__main__':
    unittest.main()
