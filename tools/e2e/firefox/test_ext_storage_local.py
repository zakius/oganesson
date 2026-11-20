"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_storage_local.js.

The add-ons' code is Firefox's, as it is. Firefox runs some tasks on each of
its two storage.local backends, a JSON file and IndexedDB, which its pref
extensions.webextensions.ExtensionStorageIDB.enabled picks. This browser has
one backend, so each task runs on it: test_storage_local_file_backend and
test_storage_local_idb_backend run the same checks, and the two
getBytesInUse tasks expect each backend's own counts, the JSON file's
(test_storage_local_file_get_bytes_in_use) and IndexedDB's, Firefox's
default. Left out: test_local_cache_invalidation's notification
extension-invalidate-storage-cache, which drops Gecko's cache of the
add-on's storage; the task's checks stay. Of head_storage.js, see
head_storage.py."""

from firefox import head_storage
from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest

LOCAL_CACHE_INVALIDATION_BACKGROUND = r'''function background(checkGet) {
  browser.test.onMessage.addListener(async msg => {
    if (msg === "set-initial") {
      await browser.storage.local.set({
        "test-prop1": "value1",
        "test-prop2": "value2",
      });
      browser.test.sendMessage("set-initial-done");
    } else if (msg === "check") {
      await checkGet("local", "test-prop1", "value1");
      await checkGet("local", "test-prop2", "value2");
      browser.test.sendMessage("check-done");
    }
  });

  browser.test.sendMessage("ready");
}'''


class StorageLocalTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)

    def test_01_local_cache_invalidation(self):
        extension = self.load_extension(
            manifest={'permissions': ['storage']},
            background=JS(LOCAL_CACHE_INVALIDATION_BACKGROUND, head_storage.CHECK_GET_IMPL))
        extension.startup()
        extension.await_message('ready')

        extension.send_message('set-initial')
        extension.await_message('set-initial-done')

        extension.send_message('check')
        extension.await_message('check-done')

        extension.unload()

    def test_02_storage_local_file_backend(self):
        head_storage.test_background_page_storage(self, 'local')

    def test_03_storage_local_idb_backend(self):
        head_storage.test_background_page_storage(self, 'local')

    def test_04_storage_local_onChanged_event_page(self):
        head_storage.test_storage_change_event_page(self, 'local')

    def test_05_storage_local_empty_events(self):
        head_storage.test_storage_empty_events(self, 'local')

    def test_06_storage_local_idb_get_bytes_in_use(self):
        head_storage.test_get_bytes_in_use(self, 'local', 'true')

    def test_07_storage_local_file_get_bytes_in_use(self):
        head_storage.test_get_bytes_in_use(self, 'local', 'false')
