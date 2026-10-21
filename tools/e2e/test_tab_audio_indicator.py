"""The "Show sound icon on tabs" setting (docs/tab-behavior.md).

A local page plays a tone (a WAV written with the stdlib wave module) in a
loop. With the setting off, the default, its tab shows no alert icon; the
switch on Settings > Appearance turns the sound icon on in open tabs. Muting
the site from the tab's context menu shows the muted icon with the setting
off, and unmuting it hides the icon again. (Chromium only lets a click on the
icon mute or unmute with the EnableTabMuting feature, off by default.) The same holds for vertical tabs.
"""

import io
import json
import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from harness import BrowserTest, Server, wait_for
from test_firefox_sync import FIND

PREF = 'oganesson.tabs.show_audio_indicator'
ALLOW = 1  # ContentSetting value in Preferences


def tone(seconds=30):
    data = io.BytesIO()
    with wave.open(data, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(i * 2 * math.pi / 20)))
                                 for i in range(8000 * seconds)))
    return data.getvalue()


# An extension that tells when the browser has the tab as audible: a missing
# sound icon then shows the setting, not a tab yet to turn audible.
MANIFEST = {
    'manifest_version': 2,
    'name': 'Audible tabs',
    'version': '1',
    'permissions': ['tabs'],
    'background': {'scripts': ['background.js']},
}

ROUTES = {
    '/tone.wav': (200, {'Content-Type': 'audio/wav'}, tone()),
    '/sound.html': (200, {'Content-Type': 'text/html'},
                    b'<!doctype html><title>sound</title>'
                    b'<audio id="a" src="/tone.wav" loop></audio>'),
}


class TabAudioIndicatorTest(BrowserTest):
    extra_prefs = {}
    tab_class = 'Tab'

    @classmethod
    def setUpClass(cls):
        cls.server = Server(ROUTES)
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-audible-'))
        (cls.folder / 'manifest.json').write_text(json.dumps(MANIFEST))
        (cls.folder / 'background.js').write_text('')
        # A fake audio output, as in test_autoplay.py; the tab still turns audible.
        cls.browser_args = ('--disable-audio-output', f'--load-extension={cls.folder}')
        cls.prefs = {'profile': {'default_content_setting_values': {'autoplay': ALLOW}},
                     **cls.extra_prefs}
        super().setUpClass()
        cls.extension = cls.browser.page('_generated_background_page.html')

    @classmethod
    def tearDownClass(cls):
        cls.extension.close()
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder)

    def setUp(self):
        self.set_pref(False)
        url = self.server.url('/sound.html')
        self.page = self.browser.new_tab(url)
        wait_for(lambda: self.page.eval(f'location.href === {json.dumps(url)}'
                                        " && document.readyState === 'complete'"), what=url)
        self.page.eval('a.play()')
        wait_for(self.audible, what='the tab to turn audible')

    def tearDown(self):
        self.browser.close_target(self.page)
        super().tearDown()

    def set_pref(self, value):
        settings = self.browser.new_tab('chrome://settings/appearance')
        try:
            wait_for(lambda: settings.eval('!!chrome.settingsPrivate'), what='settingsPrivate')
            settings.eval(f'chrome.settingsPrivate.setPref({json.dumps(PREF)}, {json.dumps(value)})')
        finally:
            self.browser.close_target(settings)

    def indicators(self):
        """The alert icons shown on tabs."""
        return [v for v in self.browser.views('AlertIndicatorButton') if v.visible]

    def audible(self):
        return self.extension.eval('new Promise(r => chrome.tabs.query({audible: true},'
                                   ' tabs => r(tabs.length)))')

    def assert_no_indicator(self):
        # The browser updates the tab's icons as it turns audible.
        self.assertTrue(self.audible())
        self.assertEqual(self.indicators(), [])

    def mute_from_context_menu(self, label):
        """Clicks `label` in the context menu of the sound tab, the last one."""
        tab = max((v for v in self.browser.views(self.tab_class) if v.visible),
                  key=lambda v: (v.bounds['y'], v.bounds['x']))
        self.browser.click_view(tab, button=3)
        item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                      for i in group if i['Title'] == label), None),
                        what=f'"{label}"')
        self.browser.click_view(item)
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def test_switch_shows_sound_icon_in_open_tabs(self):
        self.assert_no_indicator()
        page = self.browser.new_tab('chrome://settings/appearance')
        try:
            toggle = (f"({FIND})('settings-appearance-page')?.shadowRoot"
                      "?.querySelector('#showTabAudioIndicator')")
            wait_for(lambda: page.eval(f'!!{toggle}'), what='the switch')
            self.assertEqual(page.eval(f'{toggle}.label'), 'Show sound icon on tabs')
            get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
            self.assertIs(page.eval(f'{toggle}.checked'), False)
            page.eval(f'{toggle}.click()')
            wait_for(lambda: page.eval(get) is True, what='the pref on')
            wait_for(self.indicators, what='the sound icon')
            page.eval(f'{toggle}.click()')
            wait_for(lambda: page.eval(get) is False, what='the pref off')
            wait_for(lambda: not self.indicators(), what='the sound icon to go')
        finally:
            self.browser.close_target(page)

    def test_muted_icon_shows_with_setting_off(self):
        self.assert_no_indicator()
        self.mute_from_context_menu('Mute site')
        try:
            wait_for(self.indicators, what='the muted icon')
        finally:
            # The site stays muted in the profile otherwise.
            self.mute_from_context_menu('Unmute site')
        wait_for(lambda: not self.indicators(), what='the muted icon to go')
        self.assert_no_indicator()


class VerticalTabsTest(TabAudioIndicatorTest):
    extra_prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout
    tab_class = 'TabView'


if __name__ == '__main__':
    unittest.main()
