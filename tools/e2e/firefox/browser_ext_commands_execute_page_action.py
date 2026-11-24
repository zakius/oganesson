"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_commands_execute_page_action.js.

The add-ons' code is Firefox's, as it is. example.com is a local server here.
`EventUtils.synthesizeKey()` is a real key press: sendKeys() presses
Alt+Shift+J and Alt+Shift+3 in the browser window, which gets the focus
first. awaitPageActionButton() waits for the add-on's page action button in
the location bar to show and stop moving (head.wait_page_action_button()).
Firefox's page action panel is the popup bubble here, Chromium's
ExtensionPopup (head_pageAction.wait_popup_hidden()). The key press that
closes the popup (bug 1447796) goes to the window that has the focus, the
popup's, as Firefox's goes to the window that holds its panel: giving the
browser window the focus first would close the popup on its own.

Left out: add_setup()'s pref test.wait300msAfterTabSwitch, which Firefox's
test harness reads, a Gecko internal.

test_03_execute_page_action_with_matching needs the manifest's
`page_action.show_matches` (zakius/dubna#184).
"""

from firefox import head, head_pageAction
from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html'}


def script_page(url):
    return (f'<html><head><meta charset="utf-8"><script src="{url}"></script></head>'
            '<body>Test Popup</body></html>')


def send_keys(test):
    """sendKeys()."""
    test.browser.key('alt+shift+j', 'alt+shift+3')


class CommandsExecutePageActionTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/': (200, HTML, b'<!DOCTYPE html><title>example.com</title>')}

    def test_01_execute_page_action_without_popup(self):
        extension = self.load_extension(
            manifest={
                'commands': {
                    '_execute_page_action': {
                        'suggested_key': {
                            'default': 'Alt+Shift+J',
                        },
                    },
                    'send-keys-command': {
                        'suggested_key': {
                            'default': 'Alt+Shift+3',
                        },
                    },
                },
                'page_action': {},
            },

            background=JS('''function () {
      let isShown = false;

      browser.commands.onCommand.addListener(commandName => {
        if (commandName == "_execute_page_action") {
          browser.test.fail(
            `The onCommand listener should never fire for ${commandName}.`
          );
        } else if (commandName == "send-keys-command") {
          if (!isShown) {
            isShown = true;
            browser.tabs.query({ currentWindow: true, active: true }, tabs => {
              tabs.forEach(tab => {
                browser.pageAction.show(tab.id);
              });
              browser.test.sendMessage("send-keys");
            });
          }
        }
      });

      browser.pageAction.onClicked.addListener(() => {
        browser.test.assertTrue(
          isShown,
          "The onClicked event should fire if the page action is shown."
        );
        browser.test.notifyPass("page-action-without-popup");
      });

      browser.test.sendMessage("send-keys");
    }'''))

        extension.on_message('send-keys', lambda: send_keys(self))

        extension.startup()
        extension.await_finish('page-action-without-popup')
        extension.unload()

    def test_02_execute_page_action_with_popup(self):
        tab = self.open_tab('http://example.com/')

        extension = self.load_extension(
            manifest={
                'commands': {
                    '_execute_page_action': {
                        'suggested_key': {
                            'default': 'Alt+Shift+J',
                        },
                    },
                    'send-keys-command': {
                        'suggested_key': {
                            'default': 'Alt+Shift+3',
                        },
                    },
                },
                'page_action': {
                    'default_popup': 'popup.html',
                    'browser_style': True,
                },
            },

            files={
                'popup.html': script_page('popup.js'),
                'popup.js': JS('''function () {
        // TODO(Bug 2039637) consider removing this workaround along with fixing the actual underlying issue).
        window.addEventListener(
          "load",
          () => {
            browser.runtime.sendMessage("popup-opened");
          },
          { once: true }
        );
      }'''),
            },

            background=JS('''function () {
      let isShown = false;

      browser.commands.onCommand.addListener(message => {
        if (message == "_execute_page_action") {
          browser.test.fail(
            `The onCommand listener should never fire for ${message}.`
          );
        }

        if (message == "send-keys-command") {
          if (!isShown) {
            isShown = true;
            browser.tabs.query({ currentWindow: true, active: true }, tabs => {
              tabs.forEach(tab => {
                browser.pageAction.show(tab.id);
              });
              browser.test.sendMessage("send-keys-when-shown");
            });
          }
        }
      });

      browser.pageAction.onClicked.addListener(() => {
        browser.test.fail(
          `The onClicked listener should never fire when the pageAction has a popup.`
        );
      });

      browser.runtime.onMessage.addListener(msg => {
        browser.test.assertEq(msg, "popup-opened", "expected popup opened");
        browser.test.assertTrue(
          isShown,
          "The onClicked event should fire if the page action is shown."
        );
        browser.test.notifyPass("page-action-with-popup");
      });

      browser.test.sendMessage("send-keys");
    }'''))

        def send_keys_when_shown():
            head.wait_page_action_button(self, extension)
            send_keys(self)

        extension.on_message('send-keys', lambda: send_keys(self))
        extension.on_message('send-keys-when-shown', send_keys_when_shown)

        extension.startup()
        extension.await_finish('page-action-with-popup')
        extension.unload()
        self.browser.close_target(tab)

    def test_03_execute_page_action_with_matching(self):
        extension = self.load_extension(
            manifest={
                'commands': {
                    '_execute_page_action': {
                        'suggested_key': {
                            'default': 'Alt+Shift+J',
                        },
                    },
                },
                'page_action': {
                    'default_popup': 'popup.html',
                    'show_matches': ['<all_urls>'],
                    'browser_style': True,
                },
            },

            files={
                'popup.html': script_page('popup.js'),
                'popup.js': JS('''function () {
        window.addEventListener(
          "load",
          () => {
            browser.test.notifyPass("page-action-with-popup");
          },
          { once: true }
        );
      }'''),
            })

        extension.startup()
        tab = self.open_tab('http://example.com/')
        head.wait_page_action_button(self, extension)
        self.browser.key('alt+shift+j')
        # Waiting for pageAction open.
        extension.await_finish('page-action-with-popup')

        # Bug 1447796 make sure the key command can close the page action
        head_pageAction.wait_popup_shown(self)
        self.browser.xdotool('key', 'alt+shift+j')
        # Waiting for pageAction close.
        head_pageAction.wait_popup_hidden(self, extension)

        extension.unload()
        self.browser.close_target(tab)
