"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_storage_session.js.

Firefox's add-ons run in Manifest V2, as there. Left out:
test_storage_session_quota_pref_false, which turns off the quota with
Firefox's pref webextensions.storage.session.enforceQuota: this browser
always enforces it. test_storage_session_quota_pref_true, which turns it on,
runs as the default does. Of head_storage.js, see head_storage.py."""

import re

from firefox import head_storage
from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest

# Firefox's toolkit/components/extensions/test/xpcshell/data/file_sample.html
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

CONTENT_SCRIPT_BACKGROUND = r'''function background() {
  let events = [];
  browser.storage.onChanged.addListener((_, area) => {
    events.push(area);
  });
  browser.test.onMessage.addListener(_msg => {
    browser.test.sendMessage("bg-events", events.join());
  });
  browser.runtime.onMessage.addListener(async _msg => {
    await browser.storage.local.set({ foo: "local" });
    await browser.storage.session.set({ foo: "session" });
    await browser.storage.sync.set({ foo: "sync" });
    browser.test.sendMessage("done");
  });
}'''

CONTENT_SCRIPT = r'''function contentScript() {
  let events = [];
  browser.storage.onChanged.addListener((_, area) => {
    events.push(area);
  });
  browser.test.onMessage.addListener(_msg => {
    browser.test.sendMessage("cs-events", events.join());
  });

  browser.test.assertEq(
    typeof browser.storage.session,
    "undefined",
    "Expect storage.session to not be available in content scripts"
  );
  browser.runtime.sendMessage("ready");
}'''

QUOTA_BACKGROUND = r'''async function background() {
  const MB = 1_000_000;

  // Max overhead per storage item. Currently it's 16 (+ key length),
  // but that's implementation detail and might easily change.
  const SLACK = 40;

  let before = 0;
  let error = null;
  try {
    // Try to store 30Mb in session storage.
    for (let i = 0; i < 30; i++) {
      await browser.storage.session.set({
        [`key${i}`]: "x".repeat(MB),
      });

      let after = await browser.storage.session.getBytesInUse();
      let delta = after - before;
      browser.test.assertTrue(
        delta >= MB && delta <= MB + SLACK,
        `Expected storage.session.getBytesInUse() delta=${delta}`
      );
      before = after;
    }
  } catch (e) {
    error = e.message;
    browser.test.log(error);
  }

  browser.test.sendMessage("data", {
    error,
    data: await browser.storage.session.get(),
  });

  await browser.storage.session.remove(["key2", "key3"]);
  let after = await browser.storage.session.getBytesInUse();
  let delta = after - before;
  browser.test.assertTrue(
    // Note that we're expecting and comparing a negative delta here.
    -delta >= 2 * MB && -delta <= 2 * (MB + SLACK),
    `Expected getBytesInUse() after removing 2 items delta=${delta}`
  );

  error = null;
  try {
    await browser.storage.session.set({
      canary: 13,
      big: "x".repeat(5 * MB),
    });
  } catch (e) {
    error = e.message;
    browser.test.log(error);
  }
  let data = await browser.storage.session.get();

  await browser.storage.session.clear();
  let zero = await browser.storage.session.getBytesInUse();
  browser.test.assertEq(zero, 0, "Zero bytes used after clear.");

  const six = "x".repeat(6 * MB);
  await browser.storage.session.set({
    one: "x".repeat(MB),
    six: six,
  });
  before = await browser.storage.session.getBytesInUse();
  await browser.storage.session.remove("six");
  await browser.storage.session.set({ 六: six });

  after = await browser.storage.session.getBytesInUse();
  browser.test.assertEq(
    after - before,
    "六".length - "six".length,
    "Usage increased by key's length difference in js chars (not bytes)."
  );
  browser.test.assertEq("六".length, 1, "File encoding sanity check.");

  browser.test.assertEq(
    after,
    await browser.storage.session.getBytesInUse(["one", "六"]),
    "Listing all keys is equivalent to not passing any keys."
  );

  await browser.storage.session.set({ "": 13 });
  browser.test.assertEq(
    await browser.storage.session.getBytesInUse(""),
    await browser.storage.session.getBytesInUse([""]),
    `Falsy key "" is correctly interpreted.`
  );

  browser.test.sendMessage("done", { error, data });
}'''


class StorageSessionTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)
    hosts = ('example.com',)
    routes = {'/data/file_sample.html': (200, {'Content-Type': 'text/html'}, FILE_SAMPLE)}

    def test_01_storage_session(self):
        head_storage.test_background_page_storage(self, 'session')

    def test_02_storage_session_onChanged_event_page(self):
        head_storage.test_storage_change_event_page(self, 'session')

    def test_03_storage_session_persistance(self):
        head_storage.test_storage_after_reload(self, 'session', expect_persistency=False)

    def test_04_storage_session_empty_events(self):
        head_storage.test_storage_empty_events(self, 'session')

    def test_05_storage_session_contentscript(self):
        extension = self.load_extension(
            manifest={
                'content_scripts': [{
                    'matches': ['http://example.com/data/file_sample.html'],
                    'js': ['content_script.js'],
                }],
                'permissions': ['storage'],
            },
            background=JS(CONTENT_SCRIPT_BACKGROUND),
            files={'content_script.js': JS(CONTENT_SCRIPT)})
        extension.startup()

        page = self.open_tab('http://example.com/data/file_sample.html')

        extension.await_message('done')
        extension.send_message('_getEvents')

        self.assertEqual('local,sync', extension.await_message('cs-events'),
                         "Content script doesn't see storage.onChanged events from the session area.")
        self.assertEqual('local,session,sync', extension.await_message('bg-events'),
                         'Background receives onChanged events from all storage areas.')

        extension.unload()
        self.browser.close_target(page)

    def storage_session_quota(self, quota_enforced):
        extension = self.load_extension(
            manifest={'permissions': ['storage']},
            background=JS(QUOTA_BACKGROUND))
        extension.startup()

        data = extension.await_message('data', timeout=60)
        if quota_enforced:
            self.assertTrue(re.search('QuotaExceededError', data['error'] or ''),
                            f'Expect error in Nightly builds: {data["error"]}')
            self.assertEqual(len(data['data']), 10, '10Mb stored in Nightly builds.')
        else:
            self.assertIsNone(data['error'], 'No error in release builds.')
            self.assertEqual(len(data['data']), 30, '30Mb stored in release builds.')

        done = extension.await_message('done', timeout=60)
        if quota_enforced:
            self.assertTrue(re.search('QuotaExceededError', done['error'] or ''),
                            f'Expect error in Nightly builds: {done["error"]}')
            self.assertFalse(done['data'].get('canary'), 'No partial updates on error.')
        else:
            self.assertEqual(done['data'].get('canary'), 13,
                             'Without quota enforcement, canary was set.')

        extension.unload()

    def test_06_storage_session_quota_enforced_by_default(self):
        self.storage_session_quota(quota_enforced=True)

    def test_07_storage_session_quota_pref_true(self):
        self.storage_session_quota(quota_enforced=True)

    def test_08_storage_session_getBytesInUse(self):
        head_storage.test_get_bytes_in_use(self, 'session')
