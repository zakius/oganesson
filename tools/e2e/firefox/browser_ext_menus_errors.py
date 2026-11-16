"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_errors.js.

test_create_error watches the console for unchecked lastError values, as
Firefox's SimpleTest.monitorConsole() does. This browser writes them as
"Unchecked runtime.lastError: <message>"; the port reads them from the
browser's log and writes them in Firefox's form, "Unchecked lastError value:
Error: <message>", before it matches Firefox's patterns."""

import re

from extension_test_utils import JS, FirefoxTest


class MenusErrorsTest(FirefoxTest):

    def unchecked_last_errors(self, offset):
        """The unchecked lastError values in the console since `offset` of
        the browser's log, in Firefox's form."""
        with open(self.browser.log_path, errors='replace') as log:
            log.seek(offset)
            lines = log.read().splitlines()
        return [f'Unchecked lastError value: Error: {m.group(1)}' for line in lines
                if 'CONSOLE' in line
                for m in [re.search(r'Unchecked runtime\.lastError: (.*?)", source: ', line)] if m]

    def test_01_create_error(self):
        # lastError is the only means to communicate errors in the menus.create API,
        # so make sure that a warning is logged to the console if the error is not
        # checked.
        offset = self.browser.log_path.stat().st_size
        monitor = [
            # Callback exists, lastError is checked. Should not be logged.
            {'message': r'Unchecked lastError value: Error: ID already exists: some_id',
             'forbid': True},
            # No callback, lastError not checked. Should be logged.
            {'message': r'Unchecked lastError value: Error: Cannot find menu item with id noCb'},
            # Callback exists, lastError not checked. Should be logged.
            {'message': r'Unchecked lastError value: Error: Cannot find menu item with id '
                        r'cbIgnoreError'},
        ]

        background = JS('''async function background() {
            // Note: browser.menus.create returns the menu ID instead of a promise, so
            // we have to use callbacks.
            await new Promise(resolve => {
              browser.menus.create({ id: "some_id", title: "menu item" }, () => {
                browser.test.assertEq(
                  null,
                  browser.runtime.lastError,
                  "Expected no error"
                );
                resolve();
              });
            });

            // Callback exists, lastError is checked:
            await new Promise(resolve => {
              browser.menus.create({ id: "some_id", title: "menu item" }, () => {
                browser.test.assertEq(
                  "ID already exists: some_id",
                  browser.runtime.lastError.message,
                  "Expected error"
                );
                resolve();
              });
            });

            // No callback, lastError not checked:
            browser.menus.create({ id: "noCb", parentId: "noCb", title: "menu item" });

            // Callback exists, lastError not checked:
            await new Promise(resolve => {
              browser.menus.create(
                { id: "cbIgnoreError", parentId: "cbIgnoreError", title: "menu item" },
                () => {
                  resolve();
                }
              );
            });

            // Do another roundtrip with the menus API to ensure that any console
            // error messages from the previous call are flushed.
            await browser.menus.removeAll();

            browser.test.sendMessage("done");
          }''')

        extension = self.load_extension(manifest={'permissions': ['menus']},
                                        background=background)
        extension.startup()
        extension.await_message('done')
        extension.unload()

        # SimpleTest.endMonitorConsole(): each message is logged, or for
        # `forbid`, not.
        logged = self.unchecked_last_errors(offset)
        for expected in monitor:
            found = any(re.search(expected['message'], message) for message in logged)
            self.assertEqual(found, not expected.get('forbid'),
                             f"{expected['message']} {'forbidden' if expected.get('forbid') else 'expected'}"
                             f' in the console: {logged}')

    def test_02_update_error(self):
        background = JS('''async function background() {
            const id = browser.menus.create({ title: "menu item" });

            await browser.test.assertRejects(
              browser.menus.update(id, { parentId: "bogus" }),
              "Cannot find menu item with id bogus",
              "menus.update with invalid parentMenuId should fail"
            );

            await browser.test.assertRejects(
              browser.menus.update(id, { parentId: id }),
              "MenuItem cannot be an ancestor (or self) of its new parent.",
              "menus.update cannot assign itself as the parent of a menu."
            );

            await browser.test.assertRejects(
              browser.menus.update("1234", { checked: true }),
              "Cannot find menu item with id 1234",
              "menus.update with invalid menuItemId should fail"
            );

            browser.test.sendMessage("done");
          }''')

        extension = self.load_extension(manifest={'permissions': ['menus']},
                                        background=background)
        extension.startup()
        extension.await_message('done')
        extension.unload()

    def test_03_remove_error(self):
        background = JS('''async function background() {
            await browser.test.assertRejects(
              browser.menus.remove("1234"),
              "Cannot find menu item with id 1234",
              "menus.remove with invalid menuItemId should fail"
            );

            browser.test.sendMessage("done");
          }''')

        extension = self.load_extension(manifest={'permissions': ['menus']},
                                        background=background)
        extension.startup()
        extension.await_message('done')
        extension.unload()

    def test_04_invalid_documentUrlPatterns(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              await new Promise(resolve => {
                browser.menus.create(
                  {
                    title: "invalid url",
                    contexts: ["tab"],
                    documentUrlPatterns: ["test1"],
                  },
                  () => {
                    browser.test.assertEq(
                      "Invalid url pattern: test1",
                      browser.runtime.lastError.message,
                      "Expected invalid match pattern"
                    );
                    resolve();
                  }
                );
              });
              await new Promise(resolve => {
                browser.menus.create(
                  {
                    title: "invalid url",
                    contexts: ["link"],
                    targetUrlPatterns: ["test2"],
                  },
                  () => {
                    browser.test.assertEq(
                      "Invalid url pattern: test2",
                      browser.runtime.lastError.message,
                      "Expected invalid match pattern"
                    );
                    resolve();
                  }
                );
              });
              browser.test.sendMessage("done");
            }'''))
        extension.startup()
        extension.await_message('done')
        extension.unload()
