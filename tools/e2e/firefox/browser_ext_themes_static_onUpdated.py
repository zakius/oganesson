"""Port of Firefox's
toolkit/components/extensions/test/browser/browser_ext_themes_static_onUpdated.js.

Left out of test_on_updated_eventpage: assertPersistentListeners(), which
reads Gecko's primed listeners. Its terminateBackground() is the event page's
idle time, cut to a second for this browser (--event-page-idle-time)."""

import base64

from extension_test_utils import JS, FirefoxTest
from harness import wait_for

# head.js
BACKGROUND = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==')
ACCENT_COLOR = '#a14040'
TEXT_COLOR = '#fac96e'

THEME = {
    'manifest': {
        'theme': {
            'images': {
                'theme_frame': 'image1.png',
            },
            'colors': {
                'frame': ACCENT_COLOR,
                'tab_background_text': TEXT_COLOR,
            },
        },
    },
    'files': {
        'image1.png': BACKGROUND,
    },
}


class ThemesStaticOnUpdatedTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, '--event-page-idle-time=1000',
                    '--event-page-suspending-time=1000')

    def test_01_on_updated(self):
        theme = self.load_extension(**THEME)

        extension = self.load_extension(
            background=JS('''function() {
              browser.theme.onUpdated.addListener(updateInfo => {
                browser.test.sendMessage("theme-updated", updateInfo);
              });
            }'''))

        extension.startup()

        # Testing update event on static theme startup
        theme.startup()
        update_info = extension.await_message('theme-updated')
        received_theme, window_id = update_info['theme'], update_info.get('windowId')
        self.assertFalse(window_id, 'No window id in static theme update event')
        self.assertIn('image1.png', (received_theme.get('images') or {}).get('theme_frame') or '',
                      'Theme theme_frame image should be applied')
        self.assertEqual(received_theme['colors']['frame'], ACCENT_COLOR,
                         'Theme frame color should be applied')
        self.assertEqual(received_theme['colors']['tab_background_text'], TEXT_COLOR,
                         'Theme tab_background_text color should be applied')

        # Testing update event on static theme unload
        theme.unload()
        update_info = extension.await_message('theme-updated')
        self.assertFalse(window_id, 'No window id in static theme update event on unload')
        self.assertEqual(len(update_info['theme']), 0,
                         'unloading theme sends empty theme in update event')

        extension.unload()

    def test_02_on_updated_eventpage(self):
        theme = self.load_extension(**THEME)

        extension = self.load_extension(
            manifest={
                'browser_specific_settings': {'gecko': {'id': 'watcher@mochitest'}},
                'background': {'persistent': False},
            },
            background=JS('''function() {
              browser.theme.onUpdated.addListener(updateInfo => {
                browser.test.sendMessage("theme-updated", updateInfo);
              });
            }'''))

        extension.startup()

        # extension.terminateBackground(): the event page goes idle.
        wait_for(lambda: not any(t['url'].startswith(f'chrome-extension://{extension.id}/')
                                 for t in self.browser.targets()),
                 timeout=30, what='the event page to stop')

        # Testing update event on static theme startup
        theme.startup()
        update_info = extension.await_message('theme-updated')
        received_theme, window_id = update_info['theme'], update_info.get('windowId')
        self.assertFalse(window_id, 'No window id in static theme update event')
        self.assertIn('image1.png', (received_theme.get('images') or {}).get('theme_frame') or '',
                      'Theme theme_frame image should be applied')
        theme.unload()
        extension.await_message('theme-updated')

        extension.unload()
