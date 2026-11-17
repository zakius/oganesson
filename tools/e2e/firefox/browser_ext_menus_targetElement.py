"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_targetElement.js.

The add-ons' content scripts, injected with `tabs.executeScript`, get
`browser.test`, as in Firefox (extension_test_utils.py). Firefox's check
that `info.frameUrl` ends with context_frame.html, and its others, are the
add-ons' own.
"""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusTargetElementTest(head.ContextMenuTest):

    def load_extension_and_tab(self):
        """loadExtensionAndTab(): the add-on that records the menu's
        targetElementId in the current tab, and the tab."""
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus', 'http://mochi.test/*'],
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(async info => {
                browser.test.sendMessage("onShownMenu", info.targetElementId);
              });
              await browser.tabs.executeScript({ file: "contentScript.js" });
              browser.test.sendMessage("ready");
            }'''),
            files={
                'contentScript.js': JS('''function contentScript() {
                  browser.test.onMessage.addListener(
                    (msg, targetElementId, expectedSelector, description) => {
                      browser.test.assertEq("checkIsValid", msg, "Expected message");

                      let expected = expectedSelector
                        ? document.querySelector(expectedSelector)
                        : null;
                      let elem = browser.menus.getTargetElement(targetElementId);
                      browser.test.assertEq(expected, elem, description);
                      browser.test.sendMessage("checkIsValidDone");
                    }
                  );
                }'''),
            })

        extension.startup()
        extension.await_message('ready')
        return extension, tab

    def open_and_close_menu(self, extension, page, selector):
        """extension.openAndCloseMenu()."""
        head.open_context_menu(self, page, selector)
        target_element_id = extension.await_message('onShownMenu')
        head.close_context_menu(self)
        return target_element_id

    def check_is_valid(self, extension, target_element_id, expected_selector, description):
        """extension.checkIsValid()."""
        extension.send_message('checkIsValid', target_element_id, expected_selector, description)
        extension.await_message('checkIsValidDone')

    # Tests that info.targetElementId is only available with the right permissions.
    def test_01_required_permission(self):
        extension, tab = self.load_extension_and_tab()

        # Load another extension to verify that the permission from the first
        # extension does not enable the "targetElementId" parameter.
        extension2 = self.load_extension(
            manifest={
                'permissions': ['contextMenus', 'http://mochi.test/*'],
            },
            background=JS('''function background() {
              browser.contextMenus.onShown.addListener(info => {
                browser.test.assertEq(
                  undefined,
                  info.targetElementId,
                  "targetElementId requires permission"
                );
                browser.test.sendMessage("onShown");
              });
              browser.contextMenus.onClicked.addListener(async info => {
                browser.test.assertEq(
                  undefined,
                  info.targetElementId,
                  "targetElementId requires permission"
                );
                const code = `
                  browser.test.assertEq(undefined, browser.menus, "menus API requires permission in content script");
                  browser.test.assertEq(undefined, browser.contextMenus, "contextMenus API not available in content script.");
                `;
                await browser.tabs.executeScript({ code });
                browser.test.sendMessage("onClicked");
              });
              browser.contextMenus.create({ title: "menu for page" }, () => {
                browser.test.sendMessage("ready");
              });
            }'''))
        extension2.startup()
        extension2.await_message('ready')

        menu = head.open_context_menu(self, tab)
        extension.await_message('onShownMenu')
        menu_item = menu.by_label('menu for page')
        self.assertTrue(menu_item, 'the menu has the item "menu for page"')
        head.close_extension_context_menu(self, menu_item[0])

        extension2.await_message('onShown')
        extension2.await_message('onClicked')
        extension2.unload()

        extension.unload()
        self.browser.close_target(tab)

    # Tests that the basic functionality works as expected.
    def test_02_getTargetElement_in_page(self):
        extension, tab = self.load_extension_and_tab()

        for selector in ('#img1', '#link1', '#password'):
            target_element_id = self.open_and_close_menu(extension, tab, selector)
            self.check(isinstance(target_element_id, int) and not isinstance(target_element_id, bool),
                       f'targetElementId ({target_element_id}) should be an integer for {selector}')

            self.check_is_valid(extension, target_element_id, selector,
                                f'Expected target to match {selector}')

        extension.unload()
        self.browser.close_target(tab)

    def test_03_getTargetElement_in_frame(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus', 'http://mochi.test/*'],
            },
            background=JS('''async function background() {
              let targetElementId;
              browser.menus.onShown.addListener(async (info, tab) => {
                browser.test.assertTrue(
                  info.frameUrl.endsWith("context_frame.html"),
                  `Expected frame ${info.frameUrl}`
                );
                targetElementId = info.targetElementId;
                let elem = browser.menus.getTargetElement(targetElementId);
                browser.test.assertEq(
                  null,
                  elem,
                  "should not find page element in extension's background"
                );

                await browser.tabs.executeScript(tab.id, {
                  code: `{
                    let elem = browser.menus.getTargetElement(${targetElementId});
                    browser.test.assertEq(null, elem, "should not find element from different frame");
                  }`,
                });

                await browser.tabs.executeScript(tab.id, {
                  frameId: info.frameId,
                  code: `{
                    let elem = browser.menus.getTargetElement(${targetElementId});
                    browser.test.assertEq(document.body, elem, "should find the target element in the frame");
                  }`,
                });
                browser.test.sendMessage("pageAndFrameChecked");
              });

              browser.menus.onClicked.addListener(info => {
                browser.test.assertEq(
                  targetElementId,
                  info.targetElementId,
                  "targetElementId in onClicked must match onShown."
                );
                browser.test.sendMessage("onClickedChecked");
              });

              browser.menus.create(
                { title: "menu for frame", contexts: ["frame"] },
                () => {
                  browser.test.sendMessage("ready");
                }
              );
            }'''))

        extension.startup()
        extension.await_message('ready')

        menu = head.open_context_menu(self, tab, 'body', frame_index=0)
        extension.await_message('pageAndFrameChecked')
        menu_item = menu.by_label('menu for frame')
        self.assertTrue(menu_item, 'the menu has the item "menu for frame"')
        head.close_extension_context_menu(self, menu_item[0])
        extension.await_message('onClickedChecked')

        extension.unload()
        self.browser.close_target(tab)

    # Test that getTargetElement does not return a detached element.
    def test_04_getTargetElement_after_removing_element(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus', 'http://mochi.test/*'],
            },
            background=JS('''function background() {
              function contentScript(targetElementId) {
                let expectedElem = document.getElementById("edit-me");
                let { nextElementSibling } = expectedElem;

                let elem = browser.menus.getTargetElement(targetElementId);
                browser.test.assertEq(
                  expectedElem,
                  elem,
                  "Expected target element before element removal"
                );

                expectedElem.remove();
                elem = browser.menus.getTargetElement(targetElementId);
                browser.test.assertEq(
                  null,
                  elem,
                  "Expected no target element after element removal."
                );

                nextElementSibling.insertAdjacentElement("beforebegin", expectedElem);
                elem = browser.menus.getTargetElement(targetElementId);
                browser.test.assertEq(
                  expectedElem,
                  elem,
                  "Expected target element after element restoration."
                );
              }
              browser.menus.onClicked.addListener(async (info, tab) => {
                const code = `(${contentScript})(${info.targetElementId})`;
                browser.test.log(code);
                await browser.tabs.executeScript(tab.id, { code });
                browser.test.sendMessage("checkedRemovedElement");
              });
              browser.menus.create({ title: "some menu item" }, () => {
                browser.test.sendMessage("ready");
              });
            }'''))

        extension.startup()
        extension.await_message('ready')
        menu = head.open_context_menu(self, tab, '#edit-me')
        menu_item = menu.by_label('some menu item')
        self.assertTrue(menu_item, 'the menu has the item "some menu item"')
        head.close_extension_context_menu(self, menu_item[0])
        extension.await_message('checkedRemovedElement')
        extension.unload()
        self.browser.close_target(tab)

    # Tests whether targetElementId expires after opening a new menu.
    def test_05_expireTargetElement(self):
        extension, tab = self.load_extension_and_tab()

        # Open the menu once to get the first element ID.
        target_element_id = self.open_and_close_menu(extension, tab, '#longtext')

        # Open another menu. The previous ID should expire.
        self.open_and_close_menu(extension, tab, '#longtext')
        self.check_is_valid(extension, target_element_id, None,
                            'Expected initial target ID to expire after opening another menu')

        extension.unload()
        self.browser.close_target(tab)

    # Tests whether targetElementId of different tabs are independent.
    def test_06_independentMenusInDifferentTabs(self):
        extension, tab = self.load_extension_and_tab()

        target_element_id = self.open_and_close_menu(extension, tab, '#longtext')

        tab2 = self.open_tab(PAGE + '?')

        target_element_id2 = self.open_and_close_menu(extension, tab2, '#editabletext')
        if target_element_id == target_element_id2:
            # targetElementId is only guaranteed to be unique within a tab, so odds are
            # that by unlucky coincidence, that the discovered ID accidentally overlaps
            # with the actual ID.
            target_element_id2 = self.open_and_close_menu(extension, tab2, '#editabletext')
        self.check(target_element_id != target_element_id2,
                   f'targetElementId differ - Actual: {target_element_id}, {target_element_id2}')

        self.check_is_valid(extension, target_element_id2, None,
                            'targetElementId from different tab should not resolve.')
        self.check_is_valid(extension, target_element_id, '#longtext',
                            'Expected getTargetElement to work after closing a menu in another tab.')

        extension.unload()
        self.browser.close_target(tab)
        self.browser.close_target(tab2)
