"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_contentScripts_register.js.

Left out: the checks of the registered scripts' properties in Gecko's
WebExtensionPolicy (in test_contentscripts_register_all_options,
test_contentscripts_register_matchOriginAsFallback and, for
originAttributesPatterns, test_contentscripts_register_cookieStoreId); those
tasks' add-ons still register their scripts. The add-ons' code is Firefox's,
as it is.

Firefox's containers 1 to 4 are Personal, Work, Banking and Shopping, as this
browser's first four, whose cookieStoreIds are firefox-container-personal and
so on: the add-ons name those. Firefox's container 5, which no script names,
is a fifth container here, added for the test. A page in a container or a
private window opens as the user opens one: from a link's "Open link in
container" menu, or a private window's new tab."""

import json

from extension_test_utils import JS, FirefoxTest
from harness import Page, wait_for

HTML = {'Content-Type': 'text/html'}
SAMPLE = b"""<!DOCTYPE HTML>

<html>
<head>
<meta charset="utf-8">
</head>
<body>

<div id="test">Sample text</div>

</body>
</html>
"""
SAMPLE_REGISTERED_STYLES = b"""<!DOCTYPE HTML>

<html>
<head>
<meta charset="utf-8">
</head>
<body>

<div id="registered-extension-url-style">Registered Extension URL style</div>
<div id="registered-extension-text-style">Registered Extension Text style</div>

</body>
</html>
"""
CHECK_APPLIED_STYLES = JS(r'''function check_applied_styles() {
  const urlElStyle = getComputedStyle(
    document.querySelector("#registered-extension-url-style")
  );
  const blobElStyle = getComputedStyle(
    document.querySelector("#registered-extension-text-style")
  );

  browser.test.sendMessage("registered-styles-results", {
    registeredExtensionUrlStyleBG: urlElStyle["background-color"],
    registeredExtensionBlobStyleBG: blobElStyle["background-color"],
  });
}''')
# userContextId: this browser's container.
CONTAINERS = {1: 'Personal', 2: 'Work', 3: 'Banking', 4: 'Shopping', 5: 'Fifth'}


class ContentScriptsRegisterTest(FirefoxTest):
    routes = {
        '/data/file_sample.html': (200, HTML, SAMPLE),
        '/data/file_sample_registered_styles.html': (200, HTML, SAMPLE_REGISTERED_STYLES),
        '/links': (200, HTML, b'<!DOCTYPE html><a href="/data/file_sample.html">link</a>'),
    }

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    def test_01_contentscripts_register_css(self):
        background = JS(r'''async function background() {
  let cssCode = `
    #registered-extension-text-style {
      background-color: blue;
    }
  `;

  const matches = ["http://localhost/*/file_sample_registered_styles.html"];

  browser.test.assertThrows(
    () => {
      browser.contentScripts.register({
        matches,
        unknownParam: "unexpected property",
      });
    },
    /Unexpected property "unknownParam"/,
    "contentScripts.register throws on unexpected properties"
  );

  let fileScript = await browser.contentScripts.register({
    css: [{ file: "registered_ext_style.css" }],
    matches,
    runAt: "document_start",
  });

  let textScript = await browser.contentScripts.register({
    css: [{ code: cssCode }],
    matches,
    runAt: "document_start",
  });

  browser.test.onMessage.addListener(async msg => {
    switch (msg) {
      case "unregister-text":
        await textScript.unregister().catch(err => {
          browser.test.fail(
            `Unexpected exception while unregistering text style: ${err}`
          );
        });

        await browser.test.assertRejects(
          textScript.unregister(),
          /Content script already unregistered/,
          "Got the expected rejection on calling script.unregister() multiple times"
        );

        browser.test.sendMessage("unregister-text:done");
        break;
      case "unregister-file":
        await fileScript.unregister().catch(err => {
          browser.test.fail(
            `Unexpected exception while unregistering url style: ${err}`
          );
        });

        await browser.test.assertRejects(
          fileScript.unregister(),
          /Content script already unregistered/,
          "Got the expected rejection on calling script.unregister() multiple times"
        );

        browser.test.sendMessage("unregister-file:done");
        break;
      default:
        browser.test.fail(`Unexpected test message received: ${msg}`);
    }
  });

  browser.test.sendMessage("background_ready");
}''')

        extension = self.load_extension(
            manifest={
                'permissions': [
                    'http://localhost/*/file_sample_registered_styles.html',
                    '<all_urls>',
                ],
                'content_scripts': [
                    {
                        'matches': ['http://localhost/*/file_sample_registered_styles.html'],
                        'run_at': 'document_idle',
                        'js': ['check_applied_styles.js'],
                    },
                ],
            },
            background=background,
            files={
                'check_applied_styles.js': CHECK_APPLIED_STYLES,
                'registered_ext_style.css': """
        #registered-extension-url-style {
          background-color: red;
        }
      """,
            })

        extension.startup()

        extension.await_message('background_ready')

        content_page = self.open_tab('about:blank')

        self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

        registered_styles_results = extension.await_message('registered-styles-results')

        self.assertEqual(registered_styles_results['registeredExtensionUrlStyleBG'], 'rgb(255, 0, 0)',
                         'The expected style has been applied from the registered extension url style')
        self.assertEqual(registered_styles_results['registeredExtensionBlobStyleBG'], 'rgb(0, 0, 255)',
                         'The expected style has been applied from the registered extension blob style')

        extension.send_message('unregister-file')
        extension.await_message('unregister-file:done')

        self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

        unregistered_url_styles_results = extension.await_message('registered-styles-results')

        self.assertEqual(unregistered_url_styles_results['registeredExtensionUrlStyleBG'],
                         'rgba(0, 0, 0, 0)',
                         'The expected style has been applied once extension url style has been '
                         'unregistered')
        self.assertEqual(unregistered_url_styles_results['registeredExtensionBlobStyleBG'],
                         'rgb(0, 0, 255)',
                         'The expected style has been applied from the registered extension blob style')

        extension.send_message('unregister-text')
        extension.await_message('unregister-text:done')

        self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

        unregistered_blob_styles_results = extension.await_message('registered-styles-results')

        self.assertEqual(unregistered_blob_styles_results['registeredExtensionUrlStyleBG'],
                         'rgba(0, 0, 0, 0)',
                         'The expected style has been applied once extension url style has been '
                         'unregistered')
        self.assertEqual(unregistered_blob_styles_results['registeredExtensionBlobStyleBG'],
                         'rgba(0, 0, 0, 0)',
                         'The expected style has been applied once extension blob style has been '
                         'unregistered')

        self.browser.close_target(content_page)
        extension.unload()

    def test_02_contentscripts_unregister_on_context_unload(self):
        background = JS(r'''async function background() {
  const frame = document.createElement("iframe");
  frame.setAttribute("src", "/background-frame.html");

  document.body.appendChild(frame);

  browser.test.onMessage.addListener(msg => {
    switch (msg) {
      case "unload-frame":
        frame.remove();
        browser.test.sendMessage("unload-frame:done");
        break;
      default:
        browser.test.fail(`Unexpected test message received: ${msg}`);
    }
  });

  browser.test.sendMessage("background_ready");
}''')

        background_frame = JS(r'''async function background_frame() {
  await browser.contentScripts.register({
    css: [{ file: "registered_ext_style.css" }],
    matches: ["http://localhost/*/file_sample_registered_styles.html"],
    runAt: "document_start",
  });

  browser.test.sendMessage("background_frame_ready");
}''')

        extension = self.load_extension(
            manifest={
                'permissions': ['http://localhost/*/file_sample_registered_styles.html'],
                'content_scripts': [
                    {
                        'matches': ['http://localhost/*/file_sample_registered_styles.html'],
                        'run_at': 'document_idle',
                        'js': ['check_applied_styles.js'],
                    },
                ],
            },
            background=background,
            files={
                'background-frame.html': """<!DOCTYPE html>
        <html>
          <head>
            <script src="background-frame.js"></script>
          </head>
          <body>
          </body>
        </html>
      """,
                'background-frame.js': background_frame,
                'check_applied_styles.js': CHECK_APPLIED_STYLES,
                'registered_ext_style.css': """
        #registered-extension-url-style {
          background-color: red;
        }
      """,
            })

        extension.startup()

        extension.await_message('background_ready')

        # Wait the background frame to have been loaded and its script
        # executed.
        extension.await_message('background_frame_ready')

        content_page = self.open_tab('about:blank')

        self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

        registered_styles_results = extension.await_message('registered-styles-results')

        self.assertEqual(registered_styles_results['registeredExtensionUrlStyleBG'], 'rgb(255, 0, 0)',
                         'The expected style has been applied from the registered extension url style')

        extension.send_message('unload-frame')
        extension.await_message('unload-frame:done')

        self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

        unregistered_url_styles_results = extension.await_message('registered-styles-results')

        self.assertEqual(unregistered_url_styles_results['registeredExtensionUrlStyleBG'],
                         'rgba(0, 0, 0, 0)',
                         'The expected style has been applied once extension url style has been '
                         'unregistered')

        self.browser.close_target(content_page)
        extension.unload()

    def test_03_contentscripts_register_js(self):
        background = JS(r'''async function background() {
  browser.runtime.onMessage.addListener(
    ([msg, expectedStates, readyState]) => {
      if (msg == "chrome-namespace-ok") {
        browser.test.sendMessage(msg);
        return;
      }

      browser.test.assertEq("script-run", msg, "message type is correct");
      browser.test.assertTrue(
        expectedStates.includes(readyState),
        `readyState "${readyState}" is one of [${expectedStates}]`
      );
      browser.test.sendMessage("script-run-" + expectedStates[0]);
    }
  );

  // Raise an exception when the content script cannot be registered
  // because the extension has no permission to access the specified origin.

  await browser.test.assertRejects(
    browser.contentScripts.register({
      matches: ["http://*/*"],
      js: [
        {
          code: 'browser.test.fail("content script with wrong matches should not run")',
        },
      ],
    }),
    /Permission denied to register a content script for/,
    "The reject contains the expected error message"
  );

  // Register a content script from a JS code string.

  function textScriptCodeStart() {
    browser.runtime.sendMessage([
      "script-run",
      ["loading"],
      document.readyState,
    ]);
  }
  function textScriptCodeEnd() {
    browser.runtime.sendMessage([
      "script-run",
      ["interactive", "complete"],
      document.readyState,
    ]);
  }
  function textScriptCodeIdle() {
    browser.runtime.sendMessage([
      "script-run",
      ["complete"],
      document.readyState,
    ]);
  }

  // Register content scripts from both extension URLs and plain JS code strings.

  const content_scripts = [
    // Plain JS code strings.
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ code: `(${textScriptCodeStart})()` }],
      runAt: "document_start",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ code: `(${textScriptCodeEnd})()` }],
      runAt: "document_end",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ code: `(${textScriptCodeIdle})()` }],
      runAt: "document_idle",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ code: `(${textScriptCodeIdle})()` }],
      runAt: "document_idle",
      cookieStoreId: "firefox-container-personal",
    },
    // Extension URLs.
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ file: "content_script_start.js" }],
      runAt: "document_start",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ file: "content_script_end.js" }],
      runAt: "document_end",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ file: "content_script_idle.js" }],
      runAt: "document_idle",
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ file: "content_script.js" }],
      // "runAt" is not specified here to ensure that it defaults to document_idle when missing.
    },
    {
      matches: ["http://localhost/*/file_sample.html"],
      js: [{ file: "content_script_idle.js" }],
      runAt: "document_idle",
      cookieStoreId: "firefox-container-personal",
    },
  ];

  const expectedAPIs = ["unregister"];

  for (const scriptOptions of content_scripts) {
    const script = await browser.contentScripts.register(scriptOptions);
    const actualAPIs = Object.keys(script);

    browser.test.assertEq(
      JSON.stringify(expectedAPIs),
      JSON.stringify(actualAPIs),
      `Got a script API object for ${scriptOptions.js[0]}`
    );
  }

  browser.test.sendMessage("background-ready");
}''')

        content_script_start = JS(r'''function contentScriptStart() {
  browser.runtime.sendMessage([
    "script-run",
    ["loading"],
    document.readyState,
  ]);
}''')
        content_script_end = JS(r'''function contentScriptEnd() {
  browser.runtime.sendMessage([
    "script-run",
    ["interactive", "complete"],
    document.readyState,
  ]);
}''')
        content_script_idle = JS(r'''function contentScriptIdle() {
  browser.runtime.sendMessage([
    "script-run",
    ["complete"],
    document.readyState,
  ]);
}''')
        content_script = JS(r'''function contentScript() {
  let manifest = browser.runtime.getManifest();
  void manifest.permissions;
  browser.runtime.sendMessage(["chrome-namespace-ok"]);
}''')

        extension = self.load_extension(
            manifest={
                'permissions': ['http://localhost/*/file_sample.html'],
            },
            background=background,
            files={
                'content_script_start.js': content_script_start,
                'content_script_end.js': content_script_end,
                'content_script_idle.js': content_script_idle,
                'content_script.js': content_script,
            })

        counts = {'loading': 0, 'interactive': 0, 'complete': 0}
        for state in counts:
            extension.on_message(f'script-run-{state}',
                                 lambda state=state: counts.__setitem__(state, counts[state] + 1))

        content_page = self.open_tab('about:blank')

        extension.startup()
        extension.await_message('background-ready')

        self.load_url(content_page, f'{self.base_url}/file_sample.html')

        extension.await_message('chrome-namespace-ok')
        self.wait_reports(lambda: counts['complete'] == 2, 'two document_idle scripts')

        self.browser.close_target(content_page)

        # Expect two content scripts to run (one registered using an extension URL
        # and one registered from plain JS code).
        self.assertEqual(counts['loading'], 2, 'document_start script ran exactly twice')
        self.assertEqual(counts['interactive'], 2, 'document_end script ran exactly twice')
        self.assertEqual(counts['complete'], 2, 'document_idle script ran exactly twice')

        extension.unload()

    def test_04_contentscripts_register_all_options(self):
        background = JS(r'''async function background() {
  await browser.contentScripts.register({
    js: [{ file: "content_script.js" }],
    css: [{ file: "content_style.css" }],
    matches: ["http://localhost/*"],
    excludeMatches: ["http://localhost/exclude/*"],
    excludeGlobs: ["*_exclude.html"],
    includeGlobs: ["*_include.html"],
    allFrames: true,
    matchAboutBlank: true,
    runAt: "document_start",
    world: "MAIN",
    cssOrigin: "USER",
  });

  browser.test.sendMessage("background-ready", window.location.origin);
}''')

        extension = self.load_extension(
            manifest={
                'permissions': ['http://localhost/*'],
            },
            background=background,
            files={
                'content_script.js': '',
                'content_style.css': '',
            })

        extension.startup()

        extension.await_message('background-ready')
        # Left out: the script's properties in Gecko's WebExtensionPolicy.

        extension.unload()

    def test_05_contentscripts_register_matchOriginAsFallback(self):
        background = JS(r'''async function background() {
  await browser.contentScripts.register({
    js: [{ file: "cs.js" }],
    matches: ["http://localhost/*"],
    matchOriginAsFallback: true,
  });
  browser.test.sendMessage("ready");
}''')

        extension = self.load_extension(
            manifest={'permissions': ['http://localhost/*']},
            background=background,
            files={'cs.js': ''})
        extension.startup()
        extension.await_message('ready')
        # Left out: matchOriginAsFallback and matchAboutBlank in Gecko's
        # WebExtensionPolicy.

        extension.unload()

    def open_in(self, url, options):
        """ExtensionTestUtils.loadContentPage(url, options): a page in a
        container ({userContextId}, 0 for none) or a private window
        ({privateBrowsing: true})."""
        before = {t['id'] for t in self.browser.targets()}
        private = options.get('privateBrowsing')
        if private:
            self.browser.key('ctrl+shift+n')
        elif options.get('userContextId'):
            links = self.open_tab(self.server.url('/links', host='localhost'))
            try:
                self.browser.click_element(links, 'a', button=3)
                for title in ('Open link in container', CONTAINERS[options['userContextId']]):
                    self.browser.click_view(wait_for(
                        lambda title=title: next((i for menu in self.browser.menus()
                                                  for group in menu for i in group
                                                  if i['Title'] == title), None),
                        what=f'the menu item "{title}"'))
            finally:
                self.browser.close_target(links)
        else:
            return self.open_tab(url)
        page = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['id'] not in before and t['type'] == 'page'),
                                          None), what='the new tab'))
        if private:
            self.watch(page)
        self.load_url(page, url)
        return page

    def test_06_contentscripts_register_cookieStoreId(self):
        settings = self.browser.new_tab('chrome://settings/containers')
        try:
            wait_for(lambda: settings.eval('!!chrome.settingsPrivate'), what='Settings')
            settings.eval("""chrome.settingsPrivate.getPref('containers.list').then(p =>
                chrome.settingsPrivate.setPref('containers.list', [...p.value,
                    {id: 'fifth', name: 'Fifth', icon: 'tree', color: 'green'}]))""")
        finally:
            self.browser.close_target(settings)

        background = JS(r'''async function background() {
  let cookieStoreIdCSSArray = [
    { id: null, color: "rgb(123, 45, 67)" },
    { id: "firefox-private", color: "rgb(255,255,0)" },
    { id: "firefox-default", color: "red" },
    { id: "firefox-container-personal", color: "green" },
    { id: "firefox-container-work", color: "blue" },
    {
      id: ["firefox-container-banking", "firefox-container-shopping"],
      color: "rgb(100,100,0)",
    },
  ];
  const matches = ["http://localhost/*/file_sample_registered_styles.html"];

  for (let { id, color } of cookieStoreIdCSSArray) {
    await browser.contentScripts.register({
      css: [
        {
          code: `#registered-extension-text-style {
            background-color: ${color}}`,
        },
      ],
      matches,
      runAt: "document_start",
      cookieStoreId: id,
    });
  }
  await browser.test.assertRejects(
    browser.contentScripts.register({
      css: [{ code: `body {}` }],
      matches,
      cookieStoreId: "not_a_valid_cookieStoreId",
    }),
    /Invalid cookieStoreId/,
    "contentScripts.register with an invalid cookieStoreId"
  );

  if (!navigator.userAgent.includes("Android")) {
    await browser.test.assertRejects(
      browser.contentScripts.register({
        css: [{ code: `body {}` }],
        matches,
        cookieStoreId: "firefox-container-999",
      }),
      /Invalid cookieStoreId/,
      "contentScripts.register with an invalid cookieStoreId"
    );
  } else {
    // On Android, any firefox-container-... is treated as valid, so it doesn't
    // result in an error.
    // TODO bug 1743616: Fix implementation and remove this branch.
    await browser.contentScripts.register({
      css: [{ code: `body {}` }],
      matches,
      cookieStoreId: "firefox-container-999",
    });
  }

  await browser.test.assertRejects(
    browser.contentScripts.register({
      css: [{ code: `body {}` }],
      matches,
      cookieStoreId: "",
    }),
    /Invalid cookieStoreId/,
    "contentScripts.register with an invalid cookieStoreId"
  );

  browser.test.sendMessage("background_ready");
}''')

        extension = self.load_extension(
            manifest={
                'permissions': [
                    'http://localhost/*/file_sample_registered_styles.html',
                    '<all_urls>',
                ],
                'content_scripts': [
                    {
                        'matches': ['http://localhost/*/file_sample_registered_styles.html'],
                        'run_at': 'document_idle',
                        'js': ['check_applied_styles.js'],
                    },
                ],
            },
            background=background,
            files={
                'check_applied_styles.js': CHECK_APPLIED_STYLES,
            },
            incognito_override='spanning')

        extension.startup()
        extension.await_message('background_ready')
        content_script_match_tests = [
            {'contentPageOptions': {'userContextId': 5}, 'expectedStyles': 'rgb(123, 45, 67)'},
            {'contentPageOptions': {'privateBrowsing': True}, 'expectedStyles': 'rgb(255, 255, 0)'},
            {'contentPageOptions': {'userContextId': 0}, 'expectedStyles': 'rgb(255, 0, 0)'},
            {'contentPageOptions': {'userContextId': 1}, 'expectedStyles': 'rgb(0, 128, 0)'},
            {'contentPageOptions': {'userContextId': 2}, 'expectedStyles': 'rgb(0, 0, 255)'},
            {'contentPageOptions': {'userContextId': 3}, 'expectedStyles': 'rgb(100, 100, 0)'},
            {'contentPageOptions': {'userContextId': 4}, 'expectedStyles': 'rgb(100, 100, 0)'},
        ]

        for test_case in content_script_match_tests:
            options = test_case['contentPageOptions']
            # Loading initial page to preload styles and scripts
            content_page = self.open_in(f'{self.base_url}/file_sample_registered_styles.html',
                                        options)
            # Because the scripts have been registered independently, there is no
            # guarantee that the CSS has applied before the JS executes. So we discard
            # the initial result.
            extension.await_message('registered-styles-results')

            # Loading page again, to verify CSS and JS
            self.load_url(content_page, f'{self.base_url}/file_sample_registered_styles.html')

            registered_styles_results = extension.await_message('registered-styles-results')

            self.assertEqual(registered_styles_results['registeredExtensionBlobStyleBG'],
                             test_case['expectedStyles'],
                             'Expected styles applied on content page loaded with options '
                             f'{json.dumps(options)}')
            self.browser.close_target(content_page)

        extension.unload()
