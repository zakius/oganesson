"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_targetElement_shadow.js.

Each menu target is set up by Firefox's own function, which runs in the
page and returns the element that the right click aims at (head.point()).
Left out, as Gecko internals: the pref that lets the test's function run
with the system principal, and macOS's pref that keeps a right click from
selecting a word, which this browser doesn't do on Linux.
"""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusTargetElementShadowTest(head.ContextMenuTest):

    def test_01_menuInShadowDOM(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus', 'http://mochi.test/*'],
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(async (info, tab) => {
                browser.test.assertTrue(
                  Number.isInteger(info.targetElementId),
                  `${info.targetElementId} should be an integer`
                );
                browser.test.assertEq(
                  "all,link",
                  info.contexts.sort().join(","),
                  "Expected context"
                );
                browser.test.assertEq(
                  "http://example.com/?shadowlink",
                  info.linkUrl,
                  "Menu target should be a link in the shadow DOM"
                );

                let code = `{
                  try {
                    let elem = browser.menus.getTargetElement(${info.targetElementId});
                    browser.test.assertTrue(elem, "Shadow element must be found");
                    browser.test.assertEq("http://example.com/?shadowlink", elem.href, "Element is a link in shadow DOM " - elem.outerHTML);
                  } catch (e) {
                    browser.test.fail("Unexpected error in getTargetElement: " + e);
                  }
                }`;
                await browser.tabs.executeScript(tab.id, { code });
                browser.test.sendMessage(
                  "onShownMenuAndCheckedInfo",
                  info.targetElementId
                );
              });

              // Ensure that onShown is registered (workaround for bug 1300234):
              await browser.menus.removeAll();
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')

        def test_shadow_menu(setup_menu_target):
            head.open_context_menu(self, tab, JS(setup_menu_target))
            extension.await_message('onShownMenuAndCheckedInfo')
            head.close_context_menu(self)

        # Clicking in open shadow root
        test_shadow_menu('''() => {
          let doc = this.document;
          doc.body.innerHTML = `<div></div>`;
          let host = doc.body.firstElementChild.attachShadow({ mode: "open" });
          host.innerHTML = `<a href="http://example.com/?shadowlink">Test open</a>`;
          this.document.testTarget = host.firstElementChild;
          return this.document.testTarget;
        }''')

        # Clicking in closed shadow root
        test_shadow_menu('''() => {
          let doc = this.document;
          doc.body.innerHTML = `<div></div>`;
          let host = doc.body.firstElementChild.attachShadow({ mode: "closed" });
          host.innerHTML = `<a href="http://example.com/?shadowlink">Test closed</a>`;
          this.document.testTarget = host.firstElementChild;
          return this.document.testTarget;
        }''')

        # Clicking in nested shadow DOM
        test_shadow_menu('''() => {
          let doc = this.document;
          let host;
          for (let container = doc.body, i = 0; i < 10; ++i) {
            container.innerHTML = `<div id="level"></div>`;
            host = container.firstElementChild.attachShadow({ mode: "open" });
            container = host;
          }
          host.innerHTML = `<a href="http://example.com/?shadowlink">Test nested</a>`;
          this.document.testTarget = host.firstElementChild;
          return this.document.testTarget;
        }''')

        extension.unload()
        self.browser.close_target(tab)
