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
import struct
import time
import unittest
import wave

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


ROUTES = {
    '/tone.wav': (200, {'Content-Type': 'audio/wav'}, tone()),
    '/sound.html': (200, {'Content-Type': 'text/html'},
                    b'<!doctype html><title>sound</title>'
                    b'<audio id="a" src="/tone.wav" loop></audio>'),
}


class TabAudioIndicatorTest(BrowserTest):
    # A fake audio output, as in test_autoplay.py; the tab still turns audible.
    browser_args = ('--disable-audio-output',)
    extra_prefs = {}
    tab_class = 'Tab'

    @classmethod
    def setUpClass(cls):
        cls.server = Server(ROUTES)
        cls.prefs = {'profile': {'default_content_setting_values': {'autoplay': ALLOW}},
                     **cls.extra_prefs}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def setUp(self):
        self.set_pref(False)
        url = self.server.url('/sound.html')
        self.page = self.browser.new_tab(url)
        wait_for(lambda: self.page.eval(f'location.href === {json.dumps(url)}'
                                        " && document.readyState === 'complete'"), what=url)
        self.page.eval('a.play()')
        wait_for(lambda: self.page.eval('a.currentTime > 1'), what='the tone to play')

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

    def assert_no_indicator(self):
        # Long past the moment the tab turns audible and the icon fades in.
        time.sleep(3)
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

    def test_no_sound_icon_by_default(self):
        self.assert_no_indicator()

    def test_setting_shows_sound_icon_in_open_tabs(self):
        self.assert_no_indicator()
        self.set_pref(True)
        wait_for(self.indicators, what='the sound icon')
        self.set_pref(False)
        wait_for(lambda: not self.indicators(), what='the sound icon to go')

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


class SettingsPageTest(BrowserTest):

    def test_appearance_switch_sets_the_pref(self):
        page = self.browser.new_tab('chrome://settings/appearance')
        toggle = f"({FIND})('settings-appearance-page')?.shadowRoot?.querySelector('#showTabAudioIndicator')"
        wait_for(lambda: page.eval(f'!!{toggle}'), what='the switch')
        self.assertEqual(page.eval(f'{toggle}.label'), 'Show sound icon on tabs')
        get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
        self.assertIs(page.eval(f'{toggle}.checked'), False)
        self.assertIs(page.eval(get), False)
        page.eval(f'{toggle}.click()')
        wait_for(lambda: page.eval(get) is True, what='the pref on')
        page.eval(f'{toggle}.click()')
        wait_for(lambda: page.eval(get) is False, what='the pref off')


class VerticalTabsTest(TabAudioIndicatorTest):
    extra_prefs = {'vertical_tabs': {'enabled': True}}
    tab_class = 'TabView'


if __name__ == '__main__':
    unittest.main()
