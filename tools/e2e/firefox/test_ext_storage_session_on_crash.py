"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_storage_session_on_crash.js.

The add-on's code is Firefox's, as it is. Firefox's crashExtensionBackground()
crashes the add-on's process: here, the renderer of its background page,
which DevTools sends to chrome://crash. Firefox then starts the background
again on its next event (wakeupBackground()). This browser doesn't start it
again by itself: the user does, with Reload on the extensions page, which the
port does."""

import json

from extension_test_utils import JS, FirefoxTest
from harness import Page, wait_for

BACKGROUND = JS('''async function background() {
  let before = await browser.storage.session.get();

  browser.storage.session.set({ count: (before.count ?? 0) + 1 });

  // Roundtrip the data through the parent process.
  let after = await browser.storage.session.get();

  browser.test.sendMessage("data", { before, after });
}''')


class StorageSessionOnCrashTest(FirefoxTest):

    def crash_extension_background(self, extension):
        prefix = f'chrome-extension://{extension.id}/'
        target = next(t for t in self.browser.targets()
                      if t['url'].startswith(prefix) and t['type'] == 'background_page')
        page = Page(target)
        try:
            page.call('Page.navigate', url='chrome://crash')
        finally:
            page.close()
        wait_for(lambda: not any(t['id'] == target['id'] and t['url'].startswith(prefix)
                                 for t in self.browser.targets()),
                 what='the background to crash')

    def wakeup_background(self, extension):
        page = self.open_tab('chrome://extensions')
        try:
            page.eval(f'chrome.developerPrivate.reload({json.dumps(extension.id)}, '
                      '{failQuietly: true})')
        finally:
            self.browser.close_target(page)

    def storage_session_after_crash(self, persistent):
        extension = self.load_extension(
            manifest={
                'permissions': ['storage'],
                'background': {'persistent': persistent},
            },
            background=BACKGROUND)

        extension.startup()

        data = extension.await_message('data')
        self.assertEqual(json.dumps(data['before']), '{}', 'Initial before storage is empty.')
        self.assertEqual(data['after'].get('count'), 1, 'After storage counter is correct.')

        # Crashing the extension process.
        self.crash_extension_background(extension)
        self.wakeup_background(extension)

        data = extension.await_message('data')
        self.assertEqual(data['before'].get('count'), 1, 'Before storage counter is correct.')
        self.assertEqual(data['after'].get('count'), 2, 'After storage counter is correct.')

        extension.unload()

    def test_01_storage_session_after_crash_persistent(self):
        self.storage_session_after_crash(persistent=True)

    def test_02_storage_session_after_crash_event_page(self):
        self.storage_session_after_crash(persistent=False)
