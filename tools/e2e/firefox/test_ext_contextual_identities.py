"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_contextual_identities.js.

The add-ons' code is Firefox's, as it is, but for the checks of containers
turned off. This browser's containers are always on: Firefox's pref
privacy.userContext.enabled has no setting here. The test's own changes of
the pref do nothing, and its checks that the pref is on are left out. Left out
of test_contextualIdentity_with_permissions: the add-on's three checks that
the API rejects while containers are off.

Firefox's four default containers are this browser's first four, Personal,
Work, Banking and Shopping. Their cookieStoreIds are firefox-container-personal
and so on, which take the place of Firefox's firefox-container-1 and -2. The
test's own changes of containers and site associations (Firefox's
ContextualIdentityService) are the user's, in Settings (head_containers.py).
Firefox's test reads the colors and icons that it expects from
ContextualIdentityService; here they are Firefox's, as constants, with the
color codes that Firefox gives with browser.nova.enabled, which it has on.

In test_contextualIdentity_extensions_enable_containers, the add-on that
Firefox disables and enables runs its background again: the port waits for
that run's notifyPass, so that its check counts. In
test_contextualIdentity_preference_change, Firefox's second add-on has the
first one's ID, so it upgrades the first; here it is a second add-on, whose
background runs the same checks, and the port unloads both.
test_contextualIdentity_event_page needs EVENT_PAGE_ARGS, and its restart of
the add-on manager is a restart of the browser. After the restart, Firefox's
event page waits for an event; this browser starts it as it loads the add-on,
so the port awaits its "ready". Its event page stops after a second without
events, where Firefox's waits 30 seconds, so an event may start it again: the
port takes that "ready" too (await_event()).

Left out too: AddonTestUtils' start of Gecko's add-on manager (the startup
task), Gecko's ExtensionPreferencesManager setting privacy.containers in
test_contextualIdentity_extensions_enable_containers, assertPersistentListeners()
in test_contextualIdentity_event_page, which reads Gecko's primed listeners,
and in test_contextualIdentity_color_api_names the checks that the test lists
every color name of Gecko's ContextualIdentityService."""

import json

from extension_test_utils import EVENT_PAGE_ARGS, JS, FirefoxTest
from firefox import head, head_containers

# Firefox's ContextualIdentityService.containerColors with
# getContainerColorCode() under browser.nova.enabled (on in Firefox), in its
# order.
FIREFOX_COLORS = [
    ('gray', '#949297'),
    ('yellow', '#f3a81e'),
    ('orange', '#f4682c'),
    ('red', '#ed566e'),
    ('pink', '#db54bf'),
    ('purple', '#b864ee'),
    ('violet', '#764edd'),
    ('blue', '#455fe7'),
    ('cyan', '#10a4ca'),
    ('green', '#008865'),
]
# Firefox's ContextualIdentityService.containerIcons, in its order.
FIREFOX_ICONS = [
    'fingerprint', 'briefcase', 'dollar', 'cart', 'vacation', 'gift', 'food',
    'fruit', 'pet', 'tree', 'chill', 'circle', 'fence', 'robot',
]


class ContextualIdentitiesTest(FirefoxTest):
    browser_args = (*FirefoxTest.browser_args, *EVENT_PAGE_ARGS)

    def await_event(self, extension, name):
        """awaitMessage(name) for a message of the event page's listener.
        With EVENT_PAGE_ARGS the page stops after a second without events,
        where Firefox's waits 30, so it may have stopped between the test's
        steps, and the event started it again: its "ready" came first."""
        value = extension.await_message(name)
        if any(message[0] == 'ready' for message in extension.messages):
            extension.await_message('ready')
        return value

    def test_01_contextualIdentities_without_permissions(self):
        background = JS(r'''function background() {
    browser.test.assertTrue(
      !browser.contextualIdentities,
      "contextualIdentities API is not available when the contextualIdentities permission is not required"
    );
    browser.test.notifyPass("contextualIdentities_without_permission");
  }''')

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': 'testing@thing.com'},
                },
                'permissions': [],
            })

        extension.startup()
        extension.await_finish('contextualIdentities_without_permission')
        extension.unload()

    def test_02_contextualIdentities_supported_colors_and_icons(self):
        # The API must expose exactly the palette the service considers supported,
        # in the same order, so it can't silently drift from the source of truth.
        expected_colors = []
        for name, code in FIREFOX_COLORS:
            expected_colors.append({'color': name, 'colorCode': code})
        expected_icons = []
        for name in FIREFOX_ICONS:
            expected_icons.append({'icon': name,
                                   'iconUrl': f'resource://usercontext-content/{name}.svg'})

        background = JS(r'''async function background(expected) {
    let colors = await browser.contextualIdentities.getSupportedColors();
    browser.test.assertEq(
      JSON.stringify(expected.colors),
      JSON.stringify(colors),
      "getSupportedColors mirrors the colors supported by the browser"
    );

    let icons = await browser.contextualIdentities.getSupportedIcons();
    browser.test.assertEq(
      JSON.stringify(expected.icons),
      JSON.stringify(icons),
      "getSupportedIcons mirrors the icons supported by the browser"
    );

    // Shape checks that don't depend on the values computed in the parent, so a
    // service returning a well-formed object with garbage values is caught too.
    const hexMatch = /^#[0-9a-f]{6}$/;
    for (let entry of colors) {
      browser.test.assertTrue(
        hexMatch.test(entry.colorCode),
        `colorCode for ${entry.color} is a hex value (${entry.colorCode})`
      );
    }
    const iconMatch = /^resource:\/\/usercontext-content\/[a-z]+[.]svg$/;
    for (let entry of icons) {
      browser.test.assertTrue(
        iconMatch.test(entry.iconUrl),
        `iconUrl for ${entry.icon} has the expected shape (${entry.iconUrl})`
      );

      // An extension must actually be able to load the icon, so check the URL
      // resolves to a decodable image of the expected size.
      const img = new Image();
      img.src = entry.iconUrl;
      try {
        await img.decode();
      } catch (e) {
        browser.test.fail(`Failed to load image: ${img.src} - ${e}`);
      }
      browser.test.assertEq(
        32,
        img.naturalWidth,
        `Expected width for ${entry.icon}`
      );
      browser.test.assertEq(
        32,
        img.naturalHeight,
        `Expected height for ${entry.icon}`
      );
    }

    // Independent anchors with known values, so a totally broken source of
    // truth can't make the equality checks above trivially pass.
    browser.test.assertTrue(
      colors.some(c => c.color === "blue" && c.colorCode === "#455fe7"),
      "blue is exposed with its expected color code"
    );
    browser.test.assertTrue(
      icons.some(
        i =>
          i.icon === "fingerprint" &&
          i.iconUrl === "resource://usercontext-content/fingerprint.svg"
      ),
      "fingerprint is exposed with its expected icon url"
    );

    browser.test.notifyPass("contextualIdentities_supported");
  }''', json.dumps({'colors': expected_colors, 'icons': expected_icons}))

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': 'supported@thing.com'},
                },
                'permissions': ['contextualIdentities'],
            })

        extension.startup()
        extension.await_finish('contextualIdentities_supported')
        extension.unload()

    def test_03_contextualIdentity_events(self):
        background = JS(r'''async function background() {
    function createOneTimeListener(type) {
      return new Promise((resolve, reject) => {
        try {
          browser.test.assertTrue(
            type in browser.contextualIdentities,
            `Found API object browser.contextualIdentities.${type}`
          );
          const listener = change => {
            browser.test.assertTrue(
              "contextualIdentity" in change,
              `Found identity in change`
            );
            browser.contextualIdentities[type].removeListener(listener);
            resolve(change);
          };
          browser.contextualIdentities[type].addListener(listener);
        } catch (e) {
          reject(e);
        }
      });
    }

    function assertExpected(expected, container) {
      // Number of keys that are added by the APIs
      const createdCount = 2;
      for (let key of Object.keys(container)) {
        browser.test.assertTrue(key in expected, `found property ${key}`);
        browser.test.assertEq(
          expected[key],
          container[key],
          `property value for ${key} is correct`
        );
      }
      const hexMatch = /^#[0-9a-f]{6}$/;
      browser.test.assertTrue(
        hexMatch.test(expected.colorCode),
        "Color code property was expected Hex shape"
      );
      const iconMatch = /^resource:\/\/usercontext-content\/[a-z]+[.]svg$/;
      browser.test.assertTrue(
        iconMatch.test(expected.iconUrl),
        "Icon url property was expected shape"
      );
      browser.test.assertEq(
        Object.keys(expected).length,
        Object.keys(container).length + createdCount,
        "all expected properties found"
      );
    }

    let onCreatePromise = createOneTimeListener("onCreated");

    let containerObj = { name: "foobar", color: "red", icon: "circle" };
    let ci = await browser.contextualIdentities.create(containerObj);
    browser.test.assertTrue(!!ci, "We have an identity");
    const onCreateListenerResponse = await onCreatePromise;
    const cookieStoreId = ci.cookieStoreId;
    assertExpected(
      onCreateListenerResponse.contextualIdentity,
      Object.assign(containerObj, { cookieStoreId })
    );

    let onUpdatedPromise = createOneTimeListener("onUpdated");
    let updateContainerObj = { name: "testing", color: "blue", icon: "dollar" };
    ci = await browser.contextualIdentities.update(
      cookieStoreId,
      updateContainerObj
    );
    browser.test.assertTrue(!!ci, "We have an update identity");
    const onUpdatedListenerResponse = await onUpdatedPromise;
    assertExpected(
      onUpdatedListenerResponse.contextualIdentity,
      Object.assign(updateContainerObj, { cookieStoreId })
    );

    let onRemovePromise = createOneTimeListener("onRemoved");
    ci = await browser.contextualIdentities.remove(
      updateContainerObj.cookieStoreId
    );
    browser.test.assertTrue(!!ci, "We have an remove identity");
    const onRemoveListenerResponse = await onRemovePromise;
    assertExpected(
      onRemoveListenerResponse.contextualIdentity,
      Object.assign(updateContainerObj, { cookieStoreId })
    );

    browser.test.notifyPass("contextualIdentities_events");
  }''')

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': 'testing@thing.com'},
                },
                'permissions': ['contextualIdentities'],
            })

        # Firefox turns containers on here; this browser's always are.

        extension.startup()
        extension.await_finish('contextualIdentities_events')
        extension.unload()

    def test_04_contextualIdentity_site_associations(self):
        background = JS(r'''async function background() {
    function nextEvent() {
      return new Promise(resolve => {
        const listener = changeInfo => {
          browser.contextualIdentities.onSiteAssociationChanged.removeListener(
            listener
          );
          resolve(changeInfo);
        };
        browser.contextualIdentities.onSiteAssociationChanged.addListener(
          listener
        );
      });
    }

    browser.test.assertEq(
      null,
      await browser.contextualIdentities.getSiteAssociation({
        site: "example.com",
      }),
      "No association by default"
    );

    let addedPromise = nextEvent();
    await browser.contextualIdentities.setSiteAssociation({
      site: "example.com",
      cookieStoreId: "firefox-container-personal",
    });
    let added = await addedPromise;
    browser.test.assertEq("example.com", added.site, "add event site");
    browser.test.assertEq(
      "firefox-container-personal",
      added.cookieStoreId,
      "add event cookieStoreId"
    );

    browser.test.assertDeepEq(
      { site: "example.com", cookieStoreId: "firefox-container-personal" },
      await browser.contextualIdentities.getSiteAssociation({
        site: "example.com",
      }),
      "Association was set"
    );

    browser.test.assertDeepEq(
      { site: "example.com", cookieStoreId: "firefox-container-personal" },
      await browser.contextualIdentities.getSiteAssociation({
        site: "EXAMPLE.com",
      }),
      "The returned site is normalized"
    );

    let list = await browser.contextualIdentities.querySiteAssociations({});
    browser.test.assertEq(1, list.length, "One association");
    browser.test.assertEq("example.com", list[0].site, "queried site");
    browser.test.assertEq(
      "firefox-container-personal",
      list[0].cookieStoreId,
      "queried cookieStoreId"
    );

    browser.test.assertEq(
      0,
      (
        await browser.contextualIdentities.querySiteAssociations({
          cookieStoreId: "firefox-container-work",
        })
      ).length,
      "No associations for another container"
    );

    await browser.test.assertRejects(
      browser.contextualIdentities.setSiteAssociation({
        site: "example.com",
        cookieStoreId: "firefox-default",
      }),
      "Invalid contextual identity: firefox-default",
      "Cannot associate a site with the default store"
    );

    await browser.test.assertRejects(
      browser.contextualIdentities.querySiteAssociations({
        cookieStoreId: "bogus",
      }),
      "Invalid contextual identity: bogus",
      "Filtering by an invalid store rejects"
    );

    for (let site of ["", "example.com/path", "*.example.com"]) {
      await browser.test.assertRejects(
        browser.contextualIdentities.setSiteAssociation({
          site,
          cookieStoreId: "firefox-container-personal",
        }),
        `Invalid site: ${site}`,
        `${site} is rejected as a site`
      );

      await browser.test.assertRejects(
        browser.contextualIdentities.getSiteAssociation({ site }),
        `Invalid site: ${site}`,
        `${site} is rejected when getting an association`
      );
    }

    await browser.contextualIdentities.setSiteAssociation({
      site: "BÜCHER.example",
      cookieStoreId: "firefox-container-work",
    });
    browser.test.assertDeepEq(
      {
        site: "xn--bcher-kva.example",
        cookieStoreId: "firefox-container-work",
      },
      await browser.contextualIdentities.getSiteAssociation({
        site: "bücher.example",
      }),
      "An IDN site is returned encoded as ASCII"
    );
    await browser.contextualIdentities.removeSiteAssociation({
      site: "bücher.example",
    });

    let removedPromise = nextEvent();
    await browser.contextualIdentities.removeSiteAssociation({
      site: "example.com",
    });
    let removed = await removedPromise;
    browser.test.assertEq("example.com", removed.site, "remove event site");
    browser.test.assertFalse(
      "cookieStoreId" in removed,
      "remove event omits cookieStoreId"
    );

    browser.test.assertEq(
      null,
      await browser.contextualIdentities.getSiteAssociation({
        site: "example.com",
      }),
      "Association was removed"
    );

    browser.test.notifyPass("site_associations");
  }''')

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': 'site-associations@thing.com'},
                },
                'permissions': ['contextualIdentities'],
            })

        # Firefox turns containers on here; this browser's always are.

        extension.startup()
        extension.await_finish('site_associations')
        extension.unload()

    def test_05_contextualIdentity_with_permissions(self):
        background = JS(r'''async function background() {
    let ci;
    await browser.test.assertRejects(
      browser.contextualIdentities.get("foobar"),
      "Invalid contextual identity: foobar",
      "API should reject here"
    );
    await browser.test.assertRejects(
      browser.contextualIdentities.update("foobar", { name: "testing" }),
      "Invalid contextual identity: foobar",
      "API should reject for unknown updates"
    );
    await browser.test.assertRejects(
      browser.contextualIdentities.remove("foobar"),
      "Invalid contextual identity: foobar",
      "API should reject for removing unknown containers"
    );

    ci = await browser.contextualIdentities.get("firefox-container-personal");
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertTrue("name" in ci, "We have an identity.name");
    browser.test.assertTrue("color" in ci, "We have an identity.color");
    browser.test.assertTrue("icon" in ci, "We have an identity.icon");
    browser.test.assertEq("Personal", ci.name, "identity.name is correct");
    browser.test.assertEq(
      "firefox-container-personal",
      ci.cookieStoreId,
      "identity.cookieStoreId is correct"
    );

    function listenForMessage(messageName, stateChangeBool) {
      return new Promise(resolve => {
        browser.test.onMessage.addListener(function listener(msg) {
          browser.test.log(`Got message from background: ${msg}`);
          if (msg === messageName + "-response") {
            browser.test.onMessage.removeListener(listener);
            resolve();
          }
        });
        browser.test.log(
          `Sending message to background: ${messageName} ${stateChangeBool}`
        );
        browser.test.sendMessage(messageName, stateChangeBool);
      });
    }

    await listenForMessage("containers-state-change", false);

    // Left out: the checks that query(), getSupportedColors() and
    // getSupportedIcons() reject while containers are off, which they
    // never are in this browser.

    await listenForMessage("containers-state-change", true);

    let cis = await browser.contextualIdentities.query({});
    browser.test.assertEq(
      4,
      cis.length,
      "by default we should have 4 containers"
    );

    cis = await browser.contextualIdentities.query({ name: "Personal" });
    browser.test.assertEq(
      1,
      cis.length,
      "by default we should have 1 container called Personal"
    );

    cis = await browser.contextualIdentities.query({ name: "foobar" });
    browser.test.assertEq(
      0,
      cis.length,
      "by default we should have 0 container called foobar"
    );

    ci = await browser.contextualIdentities.create({
      name: "foobar",
      color: "red",
      icon: "gift",
    });
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertEq("foobar", ci.name, "identity.name is correct");
    browser.test.assertEq("red", ci.color, "identity.color is correct");
    browser.test.assertEq("gift", ci.icon, "identity.icon is correct");
    browser.test.assertTrue(
      !!ci.cookieStoreId,
      "identity.cookieStoreId is correct"
    );

    browser.test.assertRejects(
      browser.contextualIdentities.create({
        name: "foobar",
        color: "red",
        icon: "firefox",
      }),
      "Invalid icon firefox for container",
      "Create container called with an invalid icon"
    );

    browser.test.assertRejects(
      browser.contextualIdentities.create({
        name: "foobar",
        color: "firefox-orange",
        icon: "gift",
      }),
      "Invalid color name firefox-orange for container",
      "Create container called with an invalid color"
    );

    cis = await browser.contextualIdentities.query({});
    browser.test.assertEq(
      5,
      cis.length,
      "we should still have have 5 containers"
    );

    ci = await browser.contextualIdentities.get(ci.cookieStoreId);
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertEq("foobar", ci.name, "identity.name is correct");
    browser.test.assertEq("red", ci.color, "identity.color is correct");
    browser.test.assertEq("gift", ci.icon, "identity.icon is correct");

    browser.test.assertRejects(
      browser.contextualIdentities.update(ci.cookieStoreId, {
        name: "foobar",
        color: "red",
        icon: "firefox",
      }),
      "Invalid icon firefox for container",
      "Create container called with an invalid icon"
    );

    browser.test.assertRejects(
      browser.contextualIdentities.update(ci.cookieStoreId, {
        name: "foobar",
        color: "firefox-orange",
        icon: "gift",
      }),
      "Invalid color name firefox-orange for container",
      "Create container called with an invalid color"
    );

    cis = await browser.contextualIdentities.query({});
    browser.test.assertEq(5, cis.length, "now we have 5 identities");

    ci = await browser.contextualIdentities.update(ci.cookieStoreId, {
      name: "barfoo",
      color: "blue",
      icon: "cart",
    });
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertEq("barfoo", ci.name, "identity.name is correct");
    browser.test.assertEq("blue", ci.color, "identity.color is correct");
    browser.test.assertEq("cart", ci.icon, "identity.icon is correct");

    ci = await browser.contextualIdentities.get(ci.cookieStoreId);
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertEq("barfoo", ci.name, "identity.name is correct");
    browser.test.assertEq("blue", ci.color, "identity.color is correct");
    browser.test.assertEq("cart", ci.icon, "identity.icon is correct");

    ci = await browser.contextualIdentities.remove(ci.cookieStoreId);
    browser.test.assertTrue(!!ci, "We have an identity");
    browser.test.assertEq("barfoo", ci.name, "identity.name is correct");
    browser.test.assertEq("blue", ci.color, "identity.color is correct");
    browser.test.assertEq("cart", ci.icon, "identity.icon is correct");

    cis = await browser.contextualIdentities.query({});
    browser.test.assertEq(4, cis.length, "we are back to 4 identities");

    browser.test.notifyPass("contextualIdentities");
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

        def containers_state_change(state_bool):
            # Firefox turns containers off or on here; this browser's are
            # always on.
            extension.send_message('containers-state-change-response')
        extension.on_message('containers-state-change', containers_state_change)

        extension.startup()
        extension.await_finish('contextualIdentities')
        extension.unload()

    def test_06_contextualIdentity_extensions_enable_containers(self):
        background = JS(r'''async function background() {
    let ci = await browser.contextualIdentities.get("firefox-container-personal");
    browser.test.assertTrue(!!ci, "We have an identity");

    browser.test.notifyPass("contextualIdentities");
  }''')

        def make_extension(gecko_id):
            return self.load_extension(
                use_addon_manager='permanent',
                background=background,
                manifest={
                    'browser_specific_settings': {
                        'gecko': {'id': gecko_id},
                    },
                    'permissions': ['contextualIdentities'],
                })

        extension = make_extension('containers-test@mozilla.org')
        extension.startup()
        extension.await_finish('contextualIdentities')
        extension.unload()

        extension1 = make_extension('containers-test-1@mozilla.org')
        extension1.startup()
        extension1.await_finish('contextualIdentities')

        # Test that disabling leaves containers on, and that re-enabling with containers off
        # will re-enable containers.
        head.set_enabled(self, extension1, False)
        head.set_enabled(self, extension1, True)
        # The background's second run.
        extension1.await_finish('contextualIdentities')

        extension1.unload()

        extension2 = make_extension('containers-test-2@mozilla.org')
        extension3 = make_extension('containers-test-3@mozilla.org')
        extension2.startup()
        extension2.await_finish('contextualIdentities')
        extension3.startup()
        extension3.await_finish('contextualIdentities')

        # Flip the ordering to check it's still enabled
        extension3.unload()
        extension2.unload()

    def test_07_contextualIdentity_preference_change(self):
        background = JS(r'''async function background() {
    let extensionInfo = await browser.management.getSelf();
    if (extensionInfo.version == "1.0.0") {
      const containers = await browser.contextualIdentities.query({});
      browser.test.assertEq(
        containers.length,
        4,
        "We still have the original containers"
      );
      await browser.contextualIdentities.create({
        name: "foobar",
        color: "red",
        icon: "circle",
      });
    }
    const containers = await browser.contextualIdentities.query({});
    browser.test.assertEq(containers.length, 5, "We have a new container");
    if (extensionInfo.version == "1.1.0") {
      await browser.contextualIdentities.remove(containers[4].cookieStoreId);
    }
    browser.test.notifyPass("contextualIdentities");
  }''')

        def make_extension(gecko_id, version):
            return self.load_extension(
                background=background,
                manifest={
                    'version': version,
                    'browser_specific_settings': {
                        'gecko': {'id': gecko_id},
                    },
                    'permissions': ['contextualIdentities'],
                })

        extension = make_extension('containers-pref-test@mozilla.org', '1.0.0')
        extension.startup()
        extension.await_finish('contextualIdentities')

        extension2 = make_extension('containers-pref-test@mozilla.org', '1.1.0')
        extension2.startup()
        extension2.await_finish('contextualIdentities')

        extension.unload()
        extension2.unload()

    def test_08_contextualIdentity_event_page(self):
        extension = self.load_extension(
            use_addon_manager='permanent',
            manifest={
                'browser_specific_settings': {
                    'gecko': {'id': 'eventpage@mochitest'},
                },
                'permissions': ['contextualIdentities'],
                'background': {'persistent': False},
            },
            background=JS(r'''function background() {
        browser.contextualIdentities.onCreated.addListener(() => {
          browser.test.sendMessage("created");
        });
        browser.contextualIdentities.onUpdated.addListener(() => {});
        browser.contextualIdentities.onRemoved.addListener(() => {
          browser.test.sendMessage("removed");
        });
        browser.contextualIdentities.onSiteAssociationChanged.addListener(
          changeInfo => {
            browser.test.sendMessage("site-association-changed", changeInfo);
          }
        );
        browser.test.sendMessage("ready");
      }'''))

        extension.startup()
        extension.await_message('ready')

        extension.terminate_background()

        # test events waken background
        head_containers.create(self, 'foobar', 'foobar', 'circle', 'red')

        extension.await_message('ready')
        extension.await_message('created')

        # onSiteAssociationChanged does not share its registrar with the events
        # above, so check that it primes and wakes the background on its own.
        extension.terminate_background()

        head_containers.set_site_association(self, 'example.com', 'foobar')

        extension.await_message('ready')
        self.is_(
            extension.await_message('site-association-changed'),
            {
                'site': 'example.com',
                'cookieStoreId': 'firefox-container-foobar',
            },
            'A new association woke the background and was delivered')

        head_containers.remove_site_association(self, 'example.com')
        self.is_(
            self.await_event(extension, 'site-association-changed'),
            {'site': 'example.com'},
            'A removed association is delivered without a cookieStoreId')

        head_containers.remove(self, 'foobar')
        self.await_event(extension, 'removed')

        self.restart_browser()
        # The event page starts with the browser here.
        extension.await_message('ready')

        extension.unload()

    def test_09_contextualIdentity_color_api_names(self):
        # Every color name accepted by the API, see
        # https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/contextualIdentities/ContextualIdentity#color
        input_colors = [
            # Colors since inception of contextualIdentities:
            'blue',
            'turquoise',
            'green',
            'yellow',
            'orange',
            'red',
            'pink',
            'purple',
            'toolbar',
            # New colors in version 153:
            'cyan',
            'violet',
            'gray',
        ]

        # Inputs that resolve to a different name. Inputs not listed here are
        # expected to be returned unchanged.
        renamed_colors = {
            'turquoise': 'cyan',
            'toolbar': 'gray',
        }

        expectations = []
        for color in input_colors:
            expectations.append([color, renamed_colors.get(color, color)])

        background = JS(r'''async function background(colorExpectations) {
    let { cookieStoreId } = await browser.contextualIdentities.create({
      name: "color-api",
      color: "blue",
      icon: "circle",
    });

    for (let [input, expected] of colorExpectations) {
      let updated = await browser.contextualIdentities.update(cookieStoreId, {
        color: input,
      });
      browser.test.assertEq(
        expected,
        updated.color,
        `update() with "${input}" returns "${expected}"`
      );

      let fetched = await browser.contextualIdentities.get(cookieStoreId);
      browser.test.assertEq(
        expected,
        fetched.color,
        `get() after "${input}" returns "${expected}"`
      );
    }

    await browser.contextualIdentities.remove(cookieStoreId);
    browser.test.notifyPass("color-api-names");
  }''', json.dumps(expectations))

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {'gecko': {'id': 'color-api@mozilla.org'}},
                'permissions': ['contextualIdentities'],
            })

        extension.startup()
        extension.await_finish('color-api-names')
        extension.unload()

    def test_10_contextualIdentity_color_aliases_api(self):
        background = JS(r'''async function background() {
    let cyan = await browser.contextualIdentities.create({
      name: "alias-cyan",
      color: "turquoise",
      icon: "circle",
    });
    browser.test.assertEq("cyan", cyan.color, "turquoise is returned as cyan");
    browser.test.assertEq(
      "#10a4ca",
      cyan.colorCode,
      "cyan returns the refreshed code"
    );

    let gray = await browser.contextualIdentities.create({
      name: "alias-gray",
      color: "red",
      icon: "circle",
    });
    gray = await browser.contextualIdentities.update(gray.cookieStoreId, {
      name: "alias-gray",
      color: "toolbar",
      icon: "circle",
    });
    browser.test.assertEq("gray", gray.color, "toolbar is returned as gray");

    await browser.contextualIdentities.remove(cyan.cookieStoreId);
    await browser.contextualIdentities.remove(gray.cookieStoreId);

    browser.test.notifyPass("color-aliases");
  }''')

        extension = self.load_extension(
            background=background,
            manifest={
                'browser_specific_settings': {'gecko': {'id': 'color-aliases@mozilla.org'}},
                'permissions': ['contextualIdentities'],
            })

        extension.startup()
        extension.await_finish('color-aliases')
        extension.unload()
