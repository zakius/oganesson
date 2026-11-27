"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_pageAction_popup_resize.js.

The add-ons' code is Firefox's, as it is. clickPageAction() is a real click
on the add-on's page action button in the location bar
(head.click_page_action()), and awaitExtensionPanel() waits for its popup
(head_pageAction.await_extension_panel()).

Firefox's popup browser, whose size the content window's must match
(promiseContentDimensions(), head_pageAction.content_dimensions()), is the
popup's web view here, Chromium's ExtensionViewViews in the popup bubble,
read through UI DevTools. Firefox's SpecialPowers.spawn() runs the test's
function in the popup through DevTools, with `content` its window
(head_pageAction.alter_content(), which also says how the port waits for
Firefox's WebExtPopupResized event). Gecko's window.scrollMaxX and
scrollMaxY, which Chromium lacks, are the page's scroll range: the root's
scroll size less its client size. Firefox's popup is at most 800 by 600
pixels, as Chromium's is.
"""

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest

SHOW = JS('''function () {
      browser.tabs.query({ active: true, currentWindow: true }, tabs => {
        const tabId = tabs[0].id;

        browser.pageAction.show(tabId).then(() => {
          browser.test.sendMessage("action-shown");
        });
      });
    }''')

class PageActionPopupResizeTest(FirefoxTest):

    def check_size(self, popup, height, width):
        """checkSize()."""
        dims = head_pageAction.content_dimensions(self, popup)
        body, root = dims['body'], dims['root']

        self.is_(dims['window']['innerHeight'], height, f'Panel window should be {height}px tall')
        self.is_(body['clientHeight'], body['scrollHeight'],
                 'Panel body should be tall enough to fit its contents')
        self.is_(root['clientHeight'], root['scrollHeight'],
                 'Panel root should be tall enough to fit its contents')

        if width:
            self.is_(body['clientWidth'], body['scrollWidth'],
                     'Panel body should be wide enough to fit its contents')

            # Tolerate if it is 1px too wide, as that may happen with the current
            # resizing method.
            self.check(abs(dims['window']['innerWidth'] - width) <= 1,
                       f'Panel window should be {width}px wide - '
                       f"Actual: {dims['window']['innerWidth']}")

    def test_01_page_action_popup_resize(self):
        extension = self.load_extension(
            manifest={
                'page_action': {
                    'default_popup': 'popup.html',
                    'browser_style': True,
                },
            },
            background=SHOW,

            files={
                'popup.html': '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                              '<body><div></div></body></html>',
            })

        extension.startup()
        extension.await_message('action-shown')

        head.click_page_action(self, extension)

        popup = head_pageAction.await_extension_panel(self, extension)

        set_size = '''function setSize(size) {
    let elem = content.document.body.firstElementChild;
    elem.style.height = `${size}px`;
    elem.style.width = `${size}px`;
  }'''

        set_height = '''function setHeight(height) {
    content.document.body.style.overflow = "hidden";
    let elem = content.document.body.firstElementChild;
    elem.style.height = `${height}px`;
  }'''

        sizes = [200, 400, 300]

        for size in sizes:
            head_pageAction.alter_content(self, popup, set_size, size)
            self.check_size(popup, size, size)

        dims = head_pageAction.alter_content(self, popup, set_size, 1400)
        body, root = dims['body'], dims['root']

        self.is_(dims['window']['innerWidth'], 800, 'Panel window width')
        self.check(body['clientWidth'] <= 800,
                   f"Panel body width {body['clientWidth']} is less than 800")
        self.is_(body['scrollWidth'], 1400, 'Panel body scroll width')

        self.is_(dims['window']['innerHeight'], 600, 'Panel window height')
        self.check(root['clientHeight'] <= 600,
                   f"Panel root height ({root['clientHeight']}px) is less than 600px")
        self.is_(root['scrollHeight'], 1400, 'Panel root scroll height')

        for size in sizes:
            head_pageAction.alter_content(self, popup, set_height, size)
            self.check_size(popup, size, None)

        extension.unload()

    def test_02_page_action_popup_reflow(self):
        extension = self.load_extension(
            manifest={
                'page_action': {
                    'default_popup': 'popup.html',
                    'browser_style': True,
                },
            },
            background=SHOW,

            files={
                'popup.html': '''<!DOCTYPE html><html><head><meta charset="utf-8"></head>
        <body>
          The quick mauve fox jumps over the opalescent toad, with its glowing
          eyes, and its vantablack mouth, and its bottomless chasm where you
          would hope to find a heart, that looks straight into the deepest
          pits of hell. The fox shivers, and cowers, and tries to run, but
          the toad is utterly without pity. It turns, ever so slightly...
        </body>
      </html>''',
            })

        extension.startup()
        extension.await_message('action-shown')

        head.click_page_action(self, extension)

        popup = head_pageAction.await_extension_panel(self, extension)

        set_size = '''function setSize(size) {
    content.document.body.style.fontSize = `${size}px`;
  }'''

        dims = head_pageAction.alter_content(self, popup, set_size, 18)

        self.is_(dims['window']['innerWidth'], 800, 'Panel window should be 800px wide')
        self.is_(dims['body']['clientWidth'], 800, 'Panel body should be 800px wide')
        self.is_(dims['body']['clientWidth'], dims['body']['scrollWidth'],
                 'Panel body should be wide enough to fit its contents')

        self.check(dims['window']['innerHeight'] > 36,
                   f"Panel window height ({dims['window']['innerHeight']}px) should be taller "
                   'than two lines of text.')

        self.is_(dims['body']['clientHeight'], dims['body']['scrollHeight'],
                 'Panel body should be tall enough to fit its contents')
        self.is_(dims['root']['clientHeight'], dims['root']['scrollHeight'],
                 'Panel root should be tall enough to fit its contents')

        extension.unload()
