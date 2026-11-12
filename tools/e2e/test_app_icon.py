"""Settings > Appearance > App icon (docs/app-icon.md).

Choosing a variant changes the open window's icon (X11's _NET_WM_ICON) and
writes a copy of the installed .desktop entry to the user's applications
folder, with Icon= naming the variant's PNG. Choosing orange again restores
the icon and deletes the copy.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import BrowserTest, wait_for
from test_firefox_sync import FIND

PREF = 'oganesson.app_icon'
INSTALLED = ('[Desktop Entry]\nVersion=1.0\nName=oganesson\nExec=oganesson %U\nIcon=oganesson\n'
             'Type=Application\n\n[Desktop Action new-window]\nName=New Window\nExec=oganesson\n')
ORANGE, TEAL = (0xC2, 0x41, 0x0C), (0x1F, 0x5C, 0x63)


class AppIconTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.data = Path(tempfile.mkdtemp())
        (cls.data / 'system/applications').mkdir(parents=True)
        (cls.data / 'system/applications/oganesson.desktop').write_text(INSTALLED)
        cls.user_entry = cls.data / 'user/applications/oganesson.desktop'
        cls.browser_env = {'XDG_DATA_HOME': str(cls.data / 'user'),
                           'XDG_DATA_DIRS': str(cls.data / 'system')}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.data, ignore_errors=True)

    def icon_colour(self):
        """The colour at the top middle of the window's icon, inside the
        plate's edge."""
        window = subprocess.run(
            ['xdotool', 'search', '--onlyvisible', '--name', ' - oganesson$'],
            env=self.browser.env(), capture_output=True, text=True, check=False).stdout.split()
        if not window:
            return None
        # As numbers: xprop draws the icon by default.
        found = subprocess.run(['xprop', '-id', window[0], '-f', '_NET_WM_ICON', '32c',
                                ' = $0+\n', '_NET_WM_ICON'],
                               env=self.browser.env(), capture_output=True, text=True, check=False)
        numbers = [int(n) for n in re.findall(r'\d+', found.stdout.partition('=')[2])]
        if len(numbers) < 2:
            return None
        width = numbers[0]
        argb = numbers[2 + 3 * width + width // 2]
        return (argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF

    def wait_for_icon(self, colour):
        wait_for(lambda: (c := self.icon_colour()) is not None
                 and all(abs(a - b) <= 8 for a, b in zip(c, colour)),
                 what=f'the window icon in {colour}')

    def test_variant_changes_window_icon_and_desktop_entry(self):
        if self.browser.labwc:
            self.skipTest('reads the icon from X11')
        self.wait_for_icon(ORANGE)
        self.assertFalse(self.user_entry.exists())
        page = self.browser.new_tab('chrome://settings/appearance')
        try:
            dropdown = (f"({FIND})('settings-appearance-page')?.shadowRoot"
                        "?.querySelector('#appIcon')")
            wait_for(lambda: page.eval(f'!!{dropdown}'), what='the dropdown')
            self.assertEqual(page.eval(f'{dropdown}.label'), 'App icon')
            get = f'chrome.settingsPrivate.getPref({json.dumps(PREF)}).then(p => p.value)'
            self.assertEqual(page.eval(get), 'orange')

            def choose(value):
                page.eval(f"(() => {{ const s = {dropdown}.shadowRoot.querySelector('select');"
                          f" s.value = {json.dumps(value)};"
                          " s.dispatchEvent(new Event('change')); })()")
                wait_for(lambda: page.eval(get) == value, what=f'the pref {value}')

            choose('teal')
            self.wait_for_icon(TEAL)
            wait_for(self.user_entry.exists, what='the user\'s copy of the entry')
            png = Path(self.browser.binary).resolve().parent / 'app_icons/teal.png'
            self.assertTrue(png.is_file())
            lines = self.user_entry.read_text().splitlines()
            self.assertTrue(lines[0].startswith('# Written by oganesson'))
            self.assertEqual(lines[1:5], ['[Desktop Entry]', f'Icon={png}', 'TryExec=oganesson',
                                          'Version=1.0'])
            self.assertNotIn('Icon=oganesson', lines)
            self.assertIn('[Desktop Action new-window]', lines)

            choose('orange')
            self.wait_for_icon(ORANGE)
            wait_for(lambda: not self.user_entry.exists(), what='the copy to go')
        finally:
            self.browser.close_target(page)


if __name__ == '__main__':
    unittest.main()
