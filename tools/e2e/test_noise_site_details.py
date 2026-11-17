"""Fingerprinting protection per site (Helium's noise, oganesson/core/noise-site-rules.patch).

The protection page's switch is the setting's default, off as oganesson
ships it. Every http and https site's page in Site settings has a
Fingerprinting protection row, whose Allow or Block wins over the switch
from the site's next load, either way, and leaves other sites alone. Private
windows follow the switch and the sites' rules too. A switch turned on in the
helium.noise.enabled pref, where it was kept before, stays on.

The check reads back a canvas filled with one colour: with noise,
getImageData returns some pixels off by a little.
"""

import json

from harness import BrowserTest, Page, Server, wait_for

CANVAS = b"""<!doctype html><title>canvas</title>
<canvas id="c" width="32" height="32"></canvas>
<script>
const context = c.getContext('2d');
context.fillStyle = 'rgb(100, 100, 100)';
context.fillRect(0, 0, 32, 32);
const data = context.getImageData(0, 0, 32, 32).data;
window.exact = data.every((v, i) => v === (i % 4 === 3 ? 255 : 100));
</script>"""
PREF = 'helium.noise.enabled'


def row(category):
    """A site details row, through the settings page's shadow roots."""
    return f"""(() => {{ const walk = (root) => {{ for (const el of root.querySelectorAll('*')) {{
    if (el.localName === 'site-details-permission' && el.category === '{category}') return el;
    const found = el.shadowRoot && walk(el.shadowRoot); if (found) return found; }} }};
  return walk(document); }})()"""


ROW = row('helium-noise')
SELECT = f"{ROW}.shadowRoot.querySelector('#permission')"


class NoiseTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/canvas.html': (200, {'Content-Type': 'text/html'}, CANVAS)})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def settings(self):
        page = self.browser.new_tab('chrome://settings/privacy')
        wait_for(lambda: page.eval('!!window.chrome?.settingsPrivate'), what='settings')
        return page

    def protection(self):
        page = self.settings()
        on = page.eval(f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)')
        self.browser.close_target(page)
        return on

    def set_protection(self, on):
        page = self.settings()
        page.eval(f'chrome.settingsPrivate.setPref({json.dumps(PREF)}, {json.dumps(on)})')
        self.browser.close_target(page)

    def noised(self, host):
        url = self.server.url('/canvas.html', host)
        page = self.browser.new_tab(url)
        wait_for(lambda: page.eval('typeof window.exact') == 'boolean', what=url)
        exact = page.eval('exact')
        self.browser.close_target(page)
        return not exact

    def noised_in_private_window(self, host):
        url = self.server.url('/canvas.html', host)
        before = {t['id'] for t in self.browser.targets()}
        self.browser.key('ctrl+shift+n')
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['type'] == 'page' and t['id'] not in before), None),
                          what='the private window')
        page = Page(target)
        try:
            page.call('Page.navigate', url=url)
            wait_for(lambda: page.eval('location.href') == url
                     and page.eval('typeof window.exact') == 'boolean', what=url)
            return not page.eval('exact')
        finally:
            self.browser.close_window(target['id'])


class NoiseSiteDetailsTest(NoiseTest):

    def site_details(self, host):
        origin = self.server.url('/', host).rstrip('/')
        page = self.browser.new_tab(f'chrome://settings/content/siteDetails?site={origin}')
        # The page has its permissions once each row has its site.
        wait_for(lambda: page.eval(f"{row('javascript')}?.site != null"
                                   f" && {ROW}?.site != null"), what='the site details')
        return page

    def rules(self, page):
        return [rule['setting'] for rule in page.eval(
            "import('chrome://resources/js/cr.js').then(cr => "
            "cr.sendWithPromise('getExceptionList', 'helium-noise'))")]

    def choose(self, page, value):
        """Picks `value` in the row's menu, as a click on it does; the test's
        cleanup picks the default again."""
        def pick(value):
            page.eval(f"(() => {{ const s = {SELECT}; s.value = {json.dumps(value)};"
                      " s.dispatchEvent(new Event('change')); })()")
            stored = [] if value == 'default' else [value]
            wait_for(lambda: self.rules(page) == stored, what=f'the rule set to {value}')
        pick(value)
        self.addCleanup(pick, 'default')

    def test_row_while_protection_off(self):
        self.assertFalse(self.protection())
        page = self.site_details('127.0.0.1')
        self.assertTrue(page.eval(f"!{ROW}.shadowRoot.querySelector('#details').hidden"))
        self.assertIn('Fingerprinting protection', page.eval(f'{ROW}.label'))
        self.assertEqual(page.eval(f'{SELECT}.value'), 'default')
        self.assertIn('Block (default)', page.eval(f"{SELECT}.querySelector('#default').textContent"))

    def test_allow_turns_noise_on_for_the_site(self):
        self.assertFalse(self.noised('127.0.0.1'), 'no noise before the rule')
        self.choose(self.site_details('127.0.0.1'), 'allow')
        self.assertTrue(self.noised('127.0.0.1'), 'noise on the allowed site')
        self.assertFalse(self.noised('localhost'), 'no noise on another site')

    def test_block_turns_noise_off_for_the_site(self):
        self.set_protection(True)
        self.addCleanup(self.set_protection, False)
        self.assertTrue(self.noised('127.0.0.1'), 'noise before the rule')
        page = self.site_details('127.0.0.1')
        self.assertIn('Allow (default)', page.eval(f"{SELECT}.querySelector('#default').textContent"))
        self.choose(page, 'block')
        self.assertFalse(self.noised('127.0.0.1'), 'no noise on the blocked site')
        self.assertTrue(self.noised('localhost'), 'noise on another site')

    def test_private_window_follows_the_switch_and_the_site(self):
        self.assertFalse(self.noised_in_private_window('127.0.0.1'), 'no noise while off')
        self.set_protection(True)
        self.addCleanup(self.set_protection, False)
        self.assertTrue(self.noised_in_private_window('127.0.0.1'), 'noise while on')
        self.choose(self.site_details('127.0.0.1'), 'block')
        self.assertFalse(self.noised_in_private_window('127.0.0.1'), 'no noise on the blocked site')
        self.assertTrue(self.noised_in_private_window('localhost'), 'noise on another site')


class OldSwitchTest(NoiseTest):
    """A profile whose switch was turned on in the pref, before the switch
    became the setting's default."""

    prefs = {'helium': {'noise': {'enabled': True}}}

    def test_switch_stays_on(self):
        self.assertTrue(self.noised('127.0.0.1'))
        self.assertTrue(self.protection())
        self.set_protection(False)
        self.assertFalse(self.noised('127.0.0.1'))
        self.assertFalse(self.protection())
