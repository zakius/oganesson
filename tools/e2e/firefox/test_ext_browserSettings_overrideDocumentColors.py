"""Port of Firefox's
toolkit/components/extensions/test/mochitest/test_ext_browserSettings_overrideDocumentColors.html.

Firefox's test sets the user's colours (browser.display.background_color and
foreground_color), which overrideDocumentColors "always" puts on pages. This
browser's equal is the page colors theme that the user picks in its
settings: the class's `prefs` pick Dusk, applied only with increased contrast
(Firefox's default, "high-contrast-only"), and the port expects Dusk's
colours where Firefox's test expects the user's. The popup opens with a real
click on the add-on's toolbar button (AppTestDelegate.clickBrowserAction())
and closes with the window's Escape. The add-ons' code is Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest

# Chromium's PageColors::kDusk.
DUSK = 2
# Dusk's background and text colours.
DUSK_BACKGROUND = 'rgb(45, 50, 54)'
DUSK_TEXT = 'rgb(255, 255, 255)'

TEST_JS = JS('''() => {
        let {
          backgroundColor: bgColor,
          color: fgColor,
        } = window.getComputedStyle(document.body);

        document.getElementById("extStyle").disabled = true;

        let { color: defaultFgColor } = window.getComputedStyle(document.body);

        browser.test.sendMessage("test_result", {
          bgColor,
          fgColor,
          defaultFgColor,
        });
      }''')


class OverrideDocumentColorsTest(FirefoxTest):
    prefs = {'settings': {'a11y': {'requested_page_colors': DUSK,
                                   'apply_page_colors_only_on_increased_contrast': True}}}

    def with_override_document_colors(self, value, callback_after_override):
        extension = self.load_extension(
            manifest={
                'permissions': ['browserSettings'],
            },
            background=JS('''async function background(value) {
    await browser.browserSettings.overrideDocumentColors.set({ value });
    browser.test.sendMessage("settings_set");
  }''', f'"{value}"'))
        extension.startup()
        extension.await_message('settings_set')

        callback_after_override()

        extension.unload()

    def get_extension_colors(self, use_css_layers=False, use_important=False):
        layer_start = '@layer {' if use_css_layers else ''
        layer_end = '}' if use_css_layers else ''
        important = ' !important' if use_important else ''
        extension = self.load_extension(
            manifest={
                # Note: using manifest_version: 2, because browser_style has been dropped
                # from manifest_version: 3, which would result in all tests passing
                # trivially because MV3 does not have style overrides.
                'browser_action': {
                    'default_popup': 'test.html',
                    'browser_style': True,
                },
            },
            files={
                'test.html': f'''<!DOCTYPE html>
        <style id="extStyle">
        {layer_start}
        body {{
          background-color: rgb(12, 34, 56){important};
          color: rgb(98, 76, 54) {important};
        }}
        {layer_end}
        </style>
        <body><script src="test.js"></script>''',
                'test.js': TEST_JS,
            })
        extension.startup()
        popup = self.browser.open_popup(extension.id)
        try:
            result = extension.await_message('test_result')
        finally:
            popup.close()
        self.browser.key('Escape')
        extension.unload()
        return result

    def test_01_overrideDocumentColors_always(self):
        result = {}

        def check():
            result.update(self.get_extension_colors())
        self.with_override_document_colors('always', check)
        # Note: these colors are from the prefs. The colors from test.html should
        # be ignored.
        self.is_(result['bgColor'], DUSK_BACKGROUND, 'Bg color from user')
        self.is_(result['fgColor'], DUSK_TEXT, 'Fg color from user')
        self.is_(result['defaultFgColor'], DUSK_TEXT, 'Default fg color from user')

    def test_02_overrideDocumentColors_never(self):
        result = {}

        def check():
            result.update(self.get_extension_colors())
        self.with_override_document_colors('never', check)
        # Note: these colors are from test.html in get_extension_colors
        self.is_(result['bgColor'], 'rgb(12, 34, 56)', 'Bg color from extension')
        self.is_(result['fgColor'], 'rgb(98, 76, 54)', 'Fg color from extension')
        self.is_(result['defaultFgColor'], 'rgb(34, 36, 38)',  # = "color: #222426;" from extension.css
                 "Default fg color is from browser_style's extension.css")

    def test_03_with_css_cascade_layers(self):
        result = {}

        def check():
            result.update(self.get_extension_colors(use_css_layers=True))
        self.with_override_document_colors('never', check)
        self.is_(result['fgColor'], 'rgb(34, 36, 38)',  # = "color: #222426;" from extension.css
                 'Fg color from extension.css takes precedence over @layer from extension')

    def test_04_with_css_cascade_layers_and_important(self):
        result = {}

        def check():
            result.update(self.get_extension_colors(use_css_layers=True, use_important=True))
        self.with_override_document_colors('never', check)
        self.is_(result['fgColor'], 'rgb(98, 76, 54)', 'important color from extension')
