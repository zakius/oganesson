"""Firefox's ExtensionTestUtils, for Firefox's own WebExtensions tests ported
to this harness (dubna's webextensions/README.md, "Test score"; the ports are
in firefox/, and firefox_tests.py runs them).

A Firefox test loads add-ons with `ExtensionTestUtils.loadExtension({manifest,
background, files})` and checks them with `browser.test.*` calls inside the
add-on. A port keeps the add-on's code and its `browser.test` calls as Firefox
has them, and turns the test's own steps into Python:

    extension = self.load_extension(manifest={...}, background=JS('''() => {
        browser.test.assertEq("object", typeof browser.scripting);
        browser.test.sendMessage("background-done");
    }'''))
    extension.startup()
    extension.await_message('background-done')
    extension.unload()

As in Firefox, the add-on gets the default name, version and manifest version,
a Gecko ID when it has none, and its background as a script of a random name;
`JS(source)` is a function's source, which runs as `(source)()`. The add-on is
loaded and removed while the browser runs (DevTools' Extensions domain, over
the debugging pipe); `incognito_override='spanning'` lets it into private
windows, as the user does. As in Firefox, such an add-on is temporary: a
browser restart (`restart_browser()`, Firefox's promiseRestartManager())
removes it. One that a test loads with `use_addon_manager='permanent'`
restarts the browser to load it with --load-extension, as the corpus loads
add-ons, and so it stays across restarts. `on_message()` is Firefox's `extension.onMessage()`.
A test class's `hosts` and `routes` stand for Firefox's test servers, and
`open_tab()` and `load_url()` for its content pages.

The add-on's pages, background and content scripts get Firefox's `browser.test`
(`assertEq`, `assertTrue`, `assertFalse`, `assertDeepEq`, `assertThrows`,
`assertRejects`, `sendMessage`, `onMessage`, `notifyPass`, `notifyFail`,
`succeed`, `fail`, `log`), from TEST_API, which follows Firefox's ext-test.js;
so do the scripts it registers (`contentScripts.register`,
`scripting.registerContentScripts`) and those it injects with
`tabs.executeScript`.
It reports to the test through console messages, which the browser's log
keeps (a private window's, which it doesn't, through DevTools: watch()), and
`extension.send_message()` reaches its background, pages and content scripts
through DevTools. A failed assertion fails the test, as
it does in Firefox (at the test's end, so that a test reports all of them); so
does a message nobody awaited when the add-on unloads.
"""

import json
import re
import uuid

from harness import DEVELOPER_MODE, BrowserTest, Page, Server, extension_id, wait_for

# The add-on's browser.test, from Firefox's toolkit/components/extensions/
# child/ext-test.js. %TOKEN% tells this add-on's reports from others'.
TEST_API = r'''(() => {
  if (globalThis.browser && globalThis.browser.test && globalThis.browser.test.__fxtest) {
    return;
  }
  const TOKEN = "%TOKEN%";
  // An Error keeps its name and message, as Firefox's structured clone of a
  // message keeps them.
  const report = (kind, ...args) =>
    console.log("__fxtest__" + JSON.stringify({token: TOKEN, kind, args}, (key, value) =>
      value instanceof Error ? {name: value.name, message: value.message} : value));

  const errorMatches = (error, expectedError) => {
    if (typeof expectedError === "function") {
      return expectedError(error);
    }
    if (typeof error !== "object" || error == null || typeof error.message !== "string") {
      return false;
    }
    if (typeof expectedError === "string") {
      return error.message === expectedError;
    }
    try {
      return expectedError.test(error.message);
    } catch (e) {
      return false;
    }
  };
  const isPlainObject = v => Object.prototype.toString.call(v) === "[object Object]";
  const useStringInsteadOfJSON = v =>
    v === undefined || (typeof v === "number" && (isNaN(v) || !isFinite(v)));
  const deepEquals = (a, b) => {
    const NON_JSON_PREFIX = "#NOT_JSON_SERIALIZABLE#";
    const replacer = (key, value) => {
      if (typeof value == "object" && value !== null && !Array.isArray(value)) {
        if (isPlainObject(value)) {
          return Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]]));
        }
        throw new Error(`Unsupported obj type: ${Object.prototype.toString.call(value)}`);
      }
      if (useStringInsteadOfJSON(value)) {
        return `${NON_JSON_PREFIX}${value}`;
      }
      return value;
    };
    return JSON.stringify(a, replacer) === JSON.stringify(b, replacer);
  };
  const toSource = value => {
    const cannotJSONserialize = v =>
      useStringInsteadOfJSON(v) ||
      (typeof v == "object" && v !== null && !Array.isArray(v) && !isPlainObject(v));
    try {
      if (cannotJSONserialize(value)) {
        return String(value);
      }
      return JSON.stringify(value, (k, v) => (cannotJSONserialize(v) ? String(v) : v));
    } catch (e) {
      return "<unknown>";
    }
  };
  const assertTrue = (value, msg) => {
    msg = msg ?? `Assertion ${value ? "PASS" : "FAIL"}`;
    report("test-result", Boolean(value), String(msg), new Error().stack);
  };
  const assertEq = (eq, msg, expected, actual) =>
    report("test-eq", eq, String(msg), expected, actual, new Error().stack);

  const listeners = new Map();
  globalThis.__fxtestDeliver = args => {
    for (const listener of listeners.values()) {
      listener(...args);
    }
  };

  const test = {
    __fxtest: true,
    sendMessage(...args) {
      report("test-message", ...args);
    },
    notifyPass(msg) {
      report("test-done", true, msg);
    },
    notifyFail(msg) {
      report("test-done", false, msg);
    },
    log(msg) {
      report("test-log", true, msg);
    },
    fail(msg) {
      assertTrue(false, msg);
    },
    succeed(msg) {
      assertTrue(true, msg);
    },
    assertTrue(value, msg) {
      assertTrue(value, msg);
    },
    assertFalse(value, msg) {
      assertTrue(!value, msg);
    },
    assertDeepEq(expected, actual, msg) {
      structuredClone(expected);
      structuredClone(actual);
      assertEq(deepEquals(actual, expected), msg, toSource(expected), toSource(actual));
    },
    assertEq(expected, actual, msg) {
      const equal = expected === actual;
      expected = String(expected);
      actual = String(actual);
      if (!equal && expected === actual) {
        actual += " (different)";
      }
      assertEq(equal, msg, expected, actual);
    },
    assertRejects(promise, expectedError, msg) {
      promise = Promise.resolve(promise);
      return promise.then(
        () => {
          let message = `Promise resolved, expected rejection '${toSource(expectedError)}'`;
          if (msg) {
            message += `: ${msg}`;
          }
          assertTrue(false, message);
        },
        error => {
          const expected = toSource(expectedError);
          let message = `got '${toSource(error)}'`;
          if (msg) {
            message += `: ${msg}`;
          }
          assertTrue(errorMatches(error, expectedError),
                     `Promise rejected, expecting rejection to match '${expected}', ${message}`);
        });
    },
    assertThrows(func, expectedError, msg) {
      if (!expectedError) {
        throw new Error("Missing required expectedError");
      }
      try {
        func();
        let message = `Function did not throw, expected error '${toSource(expectedError)}'`;
        if (msg) {
          message += `: ${msg}`;
        }
        assertTrue(false, message);
      } catch (error) {
        const expected = toSource(expectedError);
        let message = `got '${toSource(error)}'`;
        if (msg) {
          message += `: ${msg}`;
        }
        assertTrue(errorMatches(error, expectedError),
                   `Function threw, expecting error to match '${expected}', ${message}`);
      }
    },
    onMessage: {
      addListener(callback) {
        listeners.set(callback, (...args) => {
          try {
            callback(...args);
          } catch (e) {
            assertTrue(false, `${e}\n${e.stack}`);
          }
        });
      },
      removeListener(callback) {
        listeners.delete(callback);
      },
      hasListener(callback) {
        return listeners.has(callback);
      },
    },
  };
  for (const namespace of [globalThis.browser, globalThis.chrome]) {
    if (namespace) {
      Object.defineProperty(namespace, "test", {value: test, configurable: true});
    }
  }
  // Scripts that the add-on registers get browser.test too, as in Firefox:
  // this file first, unless they run in the page's own world, where Firefox
  // gives none. The add-on doesn't see the file in what it reads back.
  const isOurs = entry => entry === "/%FILE%" || entry?.file === "/%FILE%";
  const withTestApi = (api, method, entry) => {
    const original = api && api[method];
    if (!original) {
      return;
    }
    api[method] = function (options, ...rest) {
      const add = o =>
        o && Array.isArray(o.js) && o.js.length && String(o.world).toUpperCase() !== "MAIN"
          ? {...o, js: [entry, ...o.js]}
          : o;
      return original.call(this, Array.isArray(options) ? options.map(add) : add(options), ...rest);
    };
  };
  withTestApi(globalThis.browser?.contentScripts, "register", {file: "/%FILE%"});
  withTestApi(globalThis.browser?.scripting, "registerContentScripts", "/%FILE%");
  withTestApi(globalThis.browser?.scripting, "updateContentScripts", "/%FILE%");
  const getRegistered = globalThis.browser?.scripting?.getRegisteredContentScripts;
  if (getRegistered) {
    browser.scripting.getRegisteredContentScripts = async function (...args) {
      const scripts = await getRegistered.apply(this, args);
      return scripts.map(s => (s.js ? {...s, js: s.js.filter(e => !isOurs(e))} : s));
    };
  }
  // So do the scripts it injects with tabs.executeScript(), as in Firefox:
  // this file runs first, in the same frames. A refusal refuses both.
  const executeScript = globalThis.browser?.tabs?.executeScript;
  if (executeScript) {
    browser.tabs.executeScript = function (...args) {
      const withTab = typeof args[0] !== "object" || args[0] === null;
      const details = (withTab ? args[1] : args[0]) || {};
      const ours = {file: "/%FILE%"};
      for (const key of ["allFrames", "frameId", "matchAboutBlank", "runAt"]) {
        if (details[key] !== undefined) {
          ours[key] = details[key];
        }
      }
      const run = () => executeScript.apply(this, args);
      return executeScript.call(this, ...(withTab ? [args[0]] : []), ours).then(run, run);
    };
  }
  // The background has loaded: a page's load event, or the end of a
  // worker's scripts (generate_files()).
  globalThis.__fxtestReady = () => report("ready");
  globalThis.__fxtestFlush = () => report("flush");
  if (globalThis.document) {
    addEventListener("load", globalThis.__fxtestReady, {once: true});
  }
})();
'''
TEST_API_FILE = 'fxtest-api.js'
TEST_API = TEST_API.replace('%FILE%', TEST_API_FILE)
# A test class's browser_args for a quick terminate_background(): an idle
# event page stops after a second, where Chromium's stops after 15.
EVENT_PAGE_ARGS = ('--event-page-idle-time=1000', '--event-page-suspending-time=1000')
# Firefox's ExtensionTestUtils.normalizeManifest() takes the manifest over
# this one (ExtensionXPCShellUtils.sys.mjs).
BASE_MANIFEST = {
    'browser_specific_settings': {'gecko': {'id': 'test@web.ext'}},
    'manifest_version': 2,
    'name': 'name',
    'version': '0',
}
# A report in the browser's log: `"__fxtest__{...}", source: <url> (<line>)`.
REPORT = re.compile(r'"__fxtest__(\{.*\})", source: ')


class JS:
    """A function's source, which runs as `(source)(args)`, as Firefox's tests
    pass a function for the background or a file. Each of `args` is
    JavaScript source too (json.dumps() for a value)."""

    def __init__(self, source, *args):
        self.source = source
        self.args = args

    def __str__(self):
        return f'({self.source.strip()})({", ".join(self.args)});'


def with_test_api(html):
    """An HTML file's text with the test API's script first in it."""
    tag = f'<script src="/{TEST_API_FILE}"></script>'
    match = re.search(r'<head[^>]*>|<html[^>]*>', html, re.I)
    if match:
        return html[:match.end()] + tag + html[match.end():]
    return tag + html


def generate_files(manifest, background, files):
    """The add-on's files, as Firefox's ExtensionTestCommon.generateFiles()
    makes them, with the test API added to its background, pages and content
    scripts."""
    # A file is text, JS(), bytes (an image), or JSON as a dict or list.
    files = {name: text if isinstance(text, bytes)
             else json.dumps(text) if isinstance(text, (dict, list)) else str(text)
             for name, text in (files or {}).items()}
    manifest = json.loads(json.dumps(manifest or {}))
    manifest.setdefault('name', 'Generated extension')
    manifest.setdefault('manifest_version', 2)
    manifest.setdefault('version', '1.0')
    if manifest['manifest_version'] == 2 and 'host_permissions' in manifest:
        manifest['permissions'] = (manifest.get('permissions') or []) + manifest.pop('host_permissions')
    # A Gecko ID, unless the add-on has one in Firefox's older key.
    applications = manifest.get('applications', {}).get('gecko', {})
    if 'id' not in applications:
        gecko = manifest.setdefault('browser_specific_settings', {}).setdefault('gecko', {})
        gecko.setdefault('id', '{' + str(uuid.uuid4()) + '}')
    if background is not None:
        name = f'{uuid.uuid4()}.js'
        manifest.setdefault('background', {})['scripts'] = [name]
        files[name] = str(background)
    if 'manifest.json' in files:
        manifest = json.loads(files['manifest.json'])
    # The test API, before the add-on's own scripts.
    worker = manifest.get('background', {}).get('service_worker')
    if worker:
        module = manifest['background'].get('type') == 'module'
        manifest['background']['service_worker'] = 'fxtest-worker.js'
        files['fxtest-worker.js'] = (
            f'import "/{TEST_API_FILE}"; import "/{worker}"; __fxtestReady();' if module else
            f'importScripts("/{TEST_API_FILE}", "/{worker}"); __fxtestReady();')
    if manifest.get('background', {}).get('scripts'):
        manifest['background']['scripts'].insert(0, TEST_API_FILE)
    for script in manifest.get('content_scripts', []):
        if script.get('js'):
            script['js'].insert(0, TEST_API_FILE)
    files['manifest.json'] = json.dumps(manifest)
    for name in list(files):
        if name.endswith(('.html', '.htm')):
            files[name] = with_test_api(files[name])
    return files


class Extension:
    """Firefox's ExtensionWrapper: an add-on that a test loads, starts, talks
    to and unloads."""

    def __init__(self, test, manifest=None, background=None, files=None,
                 incognito_override=None, use_addon_manager=None):
        self.test = test
        self.incognito_override = incognito_override
        self.permanent = use_addon_manager == 'permanent'
        self.folder = None
        self.token = uuid.uuid4().hex
        self.files = generate_files(manifest, background, files)
        self.manifest = json.loads(self.files['manifest.json'])
        self.files[TEST_API_FILE] = TEST_API.replace('%TOKEN%', self.token)
        self.id = None
        self.messages = []
        self.handlers = {}
        self.done = []
        self.ready = False
        self.flushed = False
        self.state = 'uninitialized'

    def startup(self):
        """Loads the add-on, and waits for its background to load."""
        folder = self.folder = self.test.browser.root / 'firefox-tests' / self.token
        for name, content in self.files.items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                (folder / name).write_bytes(content)
            else:
                (folder / name).write_text(content)
        if self.permanent:
            self.id = extension_id(folder)
            self.test.permanent.append(folder)
            self.test.restart_browser()
        else:
            self.id = self.test.browser.pipe_call('Extensions.loadUnpacked', path=str(folder))['id']
        # Only a loaded add-on is one that the test's end removes.
        self.state = 'running'
        self.test.extensions.append(self)
        if 'background' in self.manifest:
            self.test.wait_reports(lambda: self.ready, 'the background to load')
        if self.incognito_override == 'spanning':
            self.allow_in_incognito(folder)

    def allow_in_incognito(self, folder):
        """incognitoOverride: "spanning": the user lets the add-on run in
        private windows. That reloads it, so its background runs twice, where
        Firefox's runs once. Its reports start again under a new token: those
        of its first start, failures included, don't count."""
        first = self.token
        self.test.read_reports()
        self.test.failures[:] = [f for f in self.test.failures if f[0] != first]
        self.token = uuid.uuid4().hex
        (folder / TEST_API_FILE).write_text(TEST_API.replace('%TOKEN%', self.token))
        self.messages, self.done, self.ready = [], [], False
        page = self.test.browser.new_tab('chrome://extensions')
        try:
            wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
            page.eval('chrome.developerPrivate.updateExtensionConfiguration('
                      f'{{extensionId: {json.dumps(self.id)}, incognitoAccess: true}})')
        finally:
            self.test.browser.close_target(page)
        if 'background' in self.manifest:
            self.test.wait_reports(lambda: self.ready, 'the background to load again')

    def handle(self, kind, args):
        if kind == 'ready':
            self.ready = True
        elif kind == 'flush':
            self.flushed = True
        elif kind == 'test-eq':
            passed, msg, expected, actual = args[:4]
            self.test.check(passed, f'{msg} - Expected: {expected}, Actual: {actual}', self.token)
        elif kind == 'test-result':
            self.test.check(args[0], args[1], self.token)
        elif kind == 'test-done':
            self.test.check(args[0], args[1], self.token)
            self.done.append(args[1] if len(args) > 1 else None)
        elif kind == 'test-message' and args and args[0] in self.handlers:
            self.handlers[args[0]](*args[1:])
        elif kind == 'test-message':
            self.messages.append(args)

    def on_message(self, name, callback):
        """Firefox's onMessage(): `callback` gets each `name` message's
        values, which then aren't queued for await_message()."""
        self.handlers[name] = callback

    def await_message(self, name, timeout=30):
        """The first value sent with the add-on's `name` message, as
        Firefox's awaitMessage() resolves with."""
        found = self.test.wait_reports(
            lambda: next((m for m in self.messages if m and m[0] == name), None),
            f'the message {name!r}', timeout)
        self.messages.remove(found)
        return found[1] if len(found) > 1 else None

    def await_finish(self, name=None, timeout=30):
        """Waits for notifyPass() or notifyFail(), and checks its message."""
        self.test.wait_reports(lambda: self.done, 'notifyPass or notifyFail', timeout)
        actual = self.done.pop(0)
        if name:
            self.test.assertEqual(actual, name, 'test result correct')
        return actual

    def send_message(self, *args):
        """test.onMessage in the add-on's background, pages and content
        scripts."""
        prefix = f'chrome-extension://{self.id}/'
        expression = f'globalThis.__fxtestDeliver && __fxtestDeliver({json.dumps(args)})'
        for target in self.test.browser.targets():
            ours = target['url'].startswith(prefix)
            if ours and target['type'] in ('background_page', 'service_worker', 'page', 'other'):
                page = Page(target)
                try:
                    page.eval(expression, gesture=False)
                finally:
                    page.close()
            elif not ours and target['type'] in ('page', 'iframe'):
                page = Page(target)
                try:
                    for context in self.content_script_contexts(page):
                        page.call('Runtime.evaluate', expression=expression, contextId=context)
                finally:
                    page.close()

    def content_script_contexts(self, page):
        """The add-on's content scripts' worlds in `page`'s frames: Runtime.enable
        names each context that exists before it returns."""
        page.call('Runtime.enable')
        origin = f'chrome-extension://{self.id}'
        return [event['params']['context']['id'] for event in page.events
                if event.get('method') == 'Runtime.executionContextCreated'
                and event['params']['context'].get('origin') == origin
                and event['params']['context'].get('auxData', {}).get('type') == 'isolated']

    def terminate_background(self):
        """terminateBackground(): the event page goes idle and stops, quickly
        with the test class's EVENT_PAGE_ARGS."""
        prefix = f'chrome-extension://{self.id}/'
        wait_for(lambda: not any(t['url'].startswith(prefix) and t['type'] == 'background_page'
                                 for t in self.test.browser.targets()),
                 timeout=30, what='the event page to stop')

    def wakeup_background(self):
        """wakeupBackground(): the stopped event page starts again, as an
        add-on page's runtime.getBackgroundPage() starts it; here the page is
        the test API's file, which every add-on has."""
        page = self.test.browser.new_tab(f'chrome-extension://{self.id}/{TEST_API_FILE}')
        try:
            wait_for(lambda: page.eval('!!globalThis.chrome?.runtime?.getBackgroundPage'),
                     what="the add-on's page")
            page.eval('new Promise(resolve => chrome.runtime.getBackgroundPage(resolve)).then(() => 0)')
        finally:
            self.test.browser.close_target(page)

    def flush(self):
        """Waits until the background's reports so far are in the log: the
        page reports once more, and its reports come in order."""
        prefix = f'chrome-extension://{self.id}/'
        target = next((t for t in self.test.browser.targets() if t['url'].startswith(prefix)
                       and t['type'] in ('background_page', 'service_worker')), None)
        self.flushed = False
        if target:
            page = Page(target)
            try:
                page.eval('globalThis.__fxtestFlush && __fxtestFlush()', gesture=False)
            finally:
                page.close()
            self.test.wait_reports(lambda: self.flushed, "the background's reports", 10)
        else:
            self.test.read_reports()

    def unload(self, check=True):
        """Removes the add-on. With `check`, messages that no one awaited fail
        the test, as in Firefox."""
        if self.state != 'running':
            raise AssertionError('Extension not running')
        if check:
            self.flush()
        self.state = 'unloaded'
        self.test.extensions.remove(self)
        self.test.unloaded.append(self)
        if self.permanent:
            # DevTools removes only the add-ons that it loaded: the user
            # removes this one, and confirms.
            self.test.permanent.remove(self.folder)
            page = self.test.open_tab('chrome://extensions')
            browser = self.test.browser
            target = json.dumps(self.id)
            installed = f'chrome.management.getAll().then(all => all.some(e => e.id == {target}))'

            def removed():
                # The dialog ignores a click in its first moments.
                if not page.eval(installed):
                    return True
                browser.click_view(browser.wait_view('MdTextButton', Text='Remove'))
                return False

            try:
                page.call('Runtime.evaluate', expression=f'chrome.management.uninstall({target})')
                wait_for(removed, interval=0.5, what='the add-on to go')
            finally:
                browser.close_target(page)
        else:
            self.test.browser.pipe_call('Extensions.uninstall', id=self.id)
        if check:
            self.test.assertEqual(json.dumps([m[0] for m in self.messages]), '[]',
                                  'message queue is empty')


class FirefoxTest(BrowserTest):
    """A Firefox test file: one browser, and the add-ons its tasks load. Its
    tests are Firefox's add_task() functions, in order (test_01_..., test_02_...)."""

    debugging_pipe = True
    browser_args = ('--enable-unsafe-extension-debugging',)
    # Firefox's test servers (createHttpServer({hosts}), mochitest's
    # mochi.test:8888): a local HTTP server (`server`) that serves `routes`
    # (harness.Server), which these host names, with or without a port,
    # reach.
    hosts = ()
    routes = {}
    # More --host-resolver-rules, after those of `hosts`.
    host_rules = ()

    @classmethod
    def setUpClass(cls):
        # Developer mode, without which the browser disables an unpacked
        # add-on that reloads (allow_in_incognito()).
        cls.prefs = {**DEVELOPER_MODE, **(cls.prefs or {})}
        cls.server = Server(cls.routes) if cls.routes else None
        rules = [f'MAP {host} 127.0.0.1:{cls.server.port}' for host in cls.hosts]
        rules += cls.host_rules
        if rules:
            cls.browser_args = (*cls.browser_args, f'--host-resolver-rules={",".join(rules)}')
        if cls.hosts:
            # The servers speak plain HTTP, as Firefox's do: no HTTPS-Only
            # Mode, which this browser has on, nor Chromium's HTTPS-First
            # Mode in private windows.
            cls.prefs = {'https_only_mode_enabled': False,
                         'https_first_mode_incognito_enabled': False, **cls.prefs}
        super().setUpClass()
        cls.log_offset = 0

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.server:
            cls.server.stop()

    def load_url(self, page, url):
        """ContentPage.loadURL(): `page` goes to `url`, and loads."""
        page.call('Page.navigate', url=url)
        wait_for(lambda: page.eval('location.href') == url
                 and page.eval('document.readyState') == 'complete', what=f'{url} to load')

    def open_tab(self, url):
        """BrowserTestUtils.openNewForegroundTab(): a new tab at `url`, once
        it has loaded."""
        page = self.browser.new_tab(url)
        # The tab starts at about:blank, which is complete at once.
        wait_for(lambda: page.eval('document.readyState') == 'complete'
                 and (url == 'about:blank' or page.eval('location.href') != 'about:blank'),
                 what=f'{url} to load')
        return page

    def setUp(self):
        self.extensions = []
        # The folders of the add-ons loaded with use_addon_manager='permanent'.
        self.permanent = []
        # Their reports may still come, from another process: tearDown()
        # reads them.
        self.unloaded = []
        # Pages whose console the log doesn't keep (watch()).
        self.watched = []
        self.failures = []

    def tearDown(self):
        try:
            # Those a failed test left.
            for extension in list(self.extensions):
                extension.unload(check=False)
            self.read_reports()
            if self.failures:
                self.fail('browser.test: ' + ' | '.join(message for _, message in self.failures))
        finally:
            super().tearDown()

    def load_extension(self, manifest=None, background=None, files=None,
                       incognito_override=None, use_addon_manager=None):
        return Extension(self, manifest, background, files, incognito_override,
                         use_addon_manager)

    def normalize_manifest(self, manifest):
        """ExtensionTestUtils.normalizeManifest(): an add-on with `manifest`
        over Firefox's base manifest loads, and goes again. As in Firefox, the
        result's `error` is the manifest's error, here the browser's refusal
        to load it (None when it loads), and `errors` its warnings, here the
        add-on's install warnings, which chrome://extensions shows. A refusal
        is one of the `errors` too: the add-on that didn't load can't show
        that it has no warnings."""
        extension = self.load_extension(manifest={**BASE_MANIFEST, **manifest})
        try:
            extension.startup()
        except RuntimeError as refused:
            return {'error': str(refused), 'errors': [str(refused)]}
        warnings = self.browser.extension_info(extension.id)['installWarnings']
        extension.unload()
        return {'error': None, 'errors': warnings}

    def restart_browser(self):
        """AddonTestUtils.promiseRestartManager(): the browser restarts, with
        the add-ons loaded with use_addon_manager='permanent'. The others go,
        as Firefox's temporary add-ons do."""
        self.browser.quit()
        self.browser.args = [arg for arg in self.browser.args
                             if not arg.startswith('--load-extension=')]
        if self.permanent:
            self.browser.args.append(
                '--load-extension=' + ','.join(str(folder) for folder in self.permanent))
        self.browser.start()
        for extension in [e for e in self.extensions if not e.permanent]:
            extension.state = 'unloaded'
            self.extensions.remove(extension)
            self.unloaded.append(extension)

    def check(self, passed, message, token=None):
        """An assertion of the add-on's (reported under `token`): a failed one
        fails the test when it ends, as in Firefox, which runs on and reports
        every assertion."""
        if not passed:
            self.failures.append((token, message))

    def is_(self, actual, expected, message):
        """Firefox's is(), for the test's own checks: a failure fails the test
        when it ends, and the test runs on."""
        self.check(actual == expected, f'{message} - Expected: {expected}, Actual: {actual}')

    def read_reports(self):
        """Hands the add-ons' new reports in the browser's log to them."""
        by_token = {e.token: e for e in self.extensions + self.unloaded}
        with open(self.browser.log_path, 'rb') as log:
            log.seek(type(self).log_offset)
            text = log.read()
        # Up to the last whole line: the browser may be writing one.
        end = text.rfind(b'\n') + 1
        type(self).log_offset += end
        reports = [m.group(1) for line in text[:end].decode(errors='replace').splitlines()
                   for m in [REPORT.search(line)] if m]
        for page in list(self.watched):
            reports += self.console_reports(page)
        for found in reports:
            try:
                report = json.loads(found)
            except ValueError:
                continue
            extension = by_token.get(report.get('token'))
            if extension:
                extension.handle(report['kind'], report['args'])

    def watch(self, page):
        """Reads the add-ons' reports from `page`'s console through DevTools:
        the browser doesn't log a private window's console. Only the page
        target's own frames: an out-of-process frame is a target of its own."""
        page.call('Runtime.enable')
        self.watched.append(page)

    def console_reports(self, page):
        """The reports in `page`'s console since the last call."""
        try:
            page.call('Runtime.evaluate', expression='0')  # Collects the events before it.
        except (OSError, ConnectionError, RuntimeError):
            # Closed: its reports so far are in `events`.
            self.watched.remove(page)
        found = []
        for event in page.events:
            args = event.get('params', {}).get('args', [])
            value = args[0].get('value') if event.get('method') == 'Runtime.consoleAPICalled' and args else None
            if isinstance(value, str) and value.startswith('__fxtest__'):
                found.append(value[len('__fxtest__'):])
        page.events.clear()
        return found

    def wait_reports(self, check, what, timeout=30):
        def found():
            self.read_reports()
            return check()
        try:
            return wait_for(found, timeout=timeout, interval=0.1, what=what)
        except AssertionError as error:
            raise AssertionError(f'{error}; the add-ons logged: {self.console_errors()}') from None

    def console_errors(self):
        """The add-ons' last console messages other than reports, in the
        browser's log: why an add-on didn't send what a test waits for."""
        # Chromium's own extension bindings, which reject an add-on's call.
        sources = tuple(f'chrome-extension://{e.id}/' for e in self.extensions) + ('extensions::',)
        with open(self.browser.log_path, errors='replace') as log:
            lines = [line.split('] ', 1)[-1] for line in log.read().splitlines()
                     if ':CONSOLE' in line and '__fxtest__' not in line
                     and line.rstrip().split('source: ')[-1].startswith(sources)]
        return lines[-5:]
