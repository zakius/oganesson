"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_contextual_identities_move.js.

Firefox starts with four containers, as this browser does."""

from extension_test_utils import JS, FirefoxTest


class ContextualIdentitiesMoveTest(FirefoxTest):

    def test_01_contextualIdentity_move(self):
        background = JS(r'''async function background() {
  async function listCookieStoreIds() {
    const contextualIds = await browser.contextualIdentities.query({});
    return contextualIds.map(ctxId => ctxId.cookieStoreId);
  }
  const containerIds = await listCookieStoreIds();
  browser.test.assertEq(containerIds.length, 4, "We start from 4 containers");
  await browser.test.assertRejects(
    browser.contextualIdentities.move("foobar", 2),
    "Invalid contextual identity: foobar",
    "API should reject for moving unknown containers"
  );
  await browser.test.assertRejects(
    browser.contextualIdentities.move("firefox-container-123456", 2),
    "Invalid contextual identity: firefox-container-123456",
    "API should reject for moving unknown containers"
  );
  const [id0, id1, id2, id3] = containerIds;
  await browser.test.assertRejects(
    browser.contextualIdentities.move([id0, id0], 2),
    `Duplicate contextual identity: ${id0}`,
    "API should reject moves with duplicate identities containers"
  );
  await browser.test.assertRejects(
    browser.contextualIdentities.move([id0], 4),
    `Moving to invalid position 4`,
    "API should reject moves with invalid destinations"
  );
  await browser.test.assertRejects(
    browser.contextualIdentities.move([id0, id1, id2, id3], 1),
    `Moving to invalid position 1`,
    "API should reject moves with invalid destinations"
  );
  await browser.test.assertDeepEq(
    [id0, id1, id2, id3],
    await listCookieStoreIds(),
    "Rejected calls should not have modified the list"
  );
  await browser.contextualIdentities.move(id0, -1);
  await browser.test.assertDeepEq(
    [id1, id2, id3, id0],
    await listCookieStoreIds(),
    "Moving single value to last position works"
  );
  await browser.test.assertRejects(
    browser.contextualIdentities.move([id0], -2),
    `Moving to invalid position -2`,
    "API should reject moves with invalid destinations"
  );
  await browser.contextualIdentities.move([id1, id3], 1);
  await browser.test.assertDeepEq(
    [id2, id1, id3, id0],
    await listCookieStoreIds(),
    "Moving bulk values to specified position works"
  );
  await browser.contextualIdentities.move([], 2);
  await browser.test.assertDeepEq(
    [id2, id1, id3, id0],
    await listCookieStoreIds(),
    "Moving an empty list of values has no effect"
  );
  await browser.contextualIdentities.move([id0, id3, id1, id2], -1);
  await browser.test.assertDeepEq(
    [id2, id1, id3, id0],
    await listCookieStoreIds(),
    "Moving all values to the end has no effect"
  );
  browser.test.notifyPass("contextualIdentities_move");
}''')

        def make_extension(gecko_id):
            return self.load_extension(
                background=background,
                manifest={
                    'browser_specific_settings': {
                        'gecko': {'id': gecko_id},
                    },
                    'permissions': ['contextualIdentities'],
                })

        extension = make_extension('containers-test@mozilla.org')

        extension.startup()
        extension.await_finish('contextualIdentities_move')
        extension.unload()
