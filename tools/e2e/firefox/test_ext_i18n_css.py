"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_i18n_css.js.

The add-on's code is Firefox's, as it is. ContentPage.fetch() is the page's
own fetch(). Firefox's second task installs the same add-on with the add-on
manager, as a temporary add-on from an .xpi; the harness loads every add-on
from a folder, so test_02 loads it as test_01 does. Left out, as in Firefox:
the part of the task that is in `if (false)`."""

import json

from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}
FILE_SAMPLE = b"""<!DOCTYPE HTML>

<html>
<head>
<meta charset="utf-8">
</head>
<body>

<div id="test">Sample text</div>

</body>
</html>
"""

# Some multibyte characters. This sample was taken from the encoding/api-basics.html web platform test.
MULTIBYTE_STRING = 'z\xA2水\U0001D11E\U0010FFFD￾'


def get_css(a, b):
    return f"a {{ content: '{a}'; }} b {{ content: '{b}'; }}"


EXTENSION_DATA = {
    'background': JS(r'''function () {
    function backgroundFetch(url) {
      return new Promise((resolve, reject) => {
        let xhr = new XMLHttpRequest();
        xhr.overrideMimeType("text/plain");
        xhr.open("GET", url);
        xhr.onload = () => {
          resolve(xhr.responseText);
        };
        xhr.onerror = reject;
        xhr.send();
      });
    }

    Promise.all([
      backgroundFetch("foo.css"),
      backgroundFetch("bar.CsS?x#y"),
      backgroundFetch("foo.txt"),
    ]).then(results => {
      browser.test.assertEq(
        "body { max-width: 42px; }",
        results[0],
        "CSS file localized"
      );
      browser.test.assertEq(
        "body { max-width: 42px; }",
        results[1],
        "CSS file localized"
      );

      browser.test.assertEq(
        "body { __MSG_foo__; }",
        results[2],
        "Text file not localized"
      );

      browser.test.notifyPass("i18n-css");
    });

    browser.test.sendMessage("ready", browser.runtime.getURL("/"));
  }'''),

    'manifest': {
        'browser_specific_settings': {
            'gecko': {
                'id': 'i18n_css@mochi.test',
            },
        },

        'web_accessible_resources': [
            'foo.css',
            'foo.txt',
            'locale.css',
            'multibyte.css',
        ],

        'content_scripts': [
            {
                'matches': ['http://*/*/file_sample.html'],
                'css': ['foo.css'],
                'run_at': 'document_start',
            },
            {
                'matches': ['http://*/*/file_sample.html'],
                'js': ['content.js'],
            },
        ],

        'default_locale': 'en',
    },

    'files': {
        '_locales/en/messages.json': json.dumps({
            'foo': {
                'message': 'max-width: 42px',
                'description': 'foo',
            },
            'multibyteKey': {
                'message': MULTIBYTE_STRING,
            },
        }),

        'content.js': JS(r'''function () {
      let style = getComputedStyle(document.body);
      browser.test.sendMessage("content-maxWidth", style.maxWidth);
    }'''),

        'foo.css': 'body { __MSG_foo__; }',
        'bar.CsS': 'body { __MSG_foo__; }',
        'foo.txt': 'body { __MSG_foo__; }',
        'locale.css':
            '* { content: "__MSG_@@ui_locale__ __MSG_@@bidi_dir__ __MSG_@@bidi_reversed_dir__ __MSG_@@bidi_start_edge__ __MSG_@@bidi_end_edge__" }',
        'multibyte.css': get_css('__MSG_multibyteKey__', MULTIBYTE_STRING),
    },
}


class I18nCssTest(FirefoxTest):
    routes = {'/data/file_sample.html': (200, HTML, FILE_SAMPLE)}

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    @staticmethod
    def fetch(page, url):
        """ContentPage.fetch(): the page fetches `url`, as text."""
        return page.eval(f'fetch({json.dumps(url)}).then(response => response.text())')

    def run_i18n_css(self):
        extension = self.load_extension(**EXTENSION_DATA)

        extension.startup()
        base_url = extension.await_message('ready')

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        css = self.fetch(content_page, base_url + 'foo.css')

        self.is_(css, 'body { max-width: 42px; }', 'CSS file localized in mochitest scope')

        max_width = extension.await_message('content-maxWidth')

        self.is_(max_width, '42px', 'stylesheet correctly applied')

        css = self.fetch(content_page, base_url + 'locale.css')
        self.is_(css, '* { content: "en-US ltr rtl left right" }',
                 'CSS file localized in mochitest scope')

        css = self.fetch(content_page, base_url + 'multibyte.css')
        self.is_(css, get_css(MULTIBYTE_STRING, MULTIBYTE_STRING),
                 'CSS file contains multibyte string')

        self.browser.close_target(content_page)

        extension.await_finish('i18n-css')
        extension.unload()

    def test_01_i18n_css(self):
        self.run_i18n_css()

    def test_02_i18n_css_xpi(self):
        self.run_i18n_css()
