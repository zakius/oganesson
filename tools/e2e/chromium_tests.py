#!/usr/bin/env python3
"""Chromium's own extension API tests, run as Chrome extensions (dubna's
webextensions/README.md, "Firefox add-ons only"): what the WebExtensions climb
changes must leave a Chrome extension's Chromium as it is.

  chromium_tests.py [--only TEST[,TEST...]] [--baseline] [--jobs N]

The tests are the test extensions in Chromium's
chrome/test/data/extensions/api_test/, of the namespaces in NAMESPACES, at the
Chromium version oganesson builds (helium/chromium_version.txt), downloaded once
into work/chromium-tests/<version>/. A test is a folder with a manifest and a
background or a test.html; it checks its own results with chrome.test.* and
ends with notifyPass() or notifyFail(). Each one runs unpacked, without a gecko
key, in a browser of its own, --jobs at a time. A script that runs first
records how it ends, and gives chrome.test.getConfig() the local server's port:
every host goes to that server, which serves api_test/ under
/extensions/api_test/.

Many tests need more than that: Chromium's C++ test fixture (policies, a
second extension, chrome.test.sendMessage() replies, other test data). Stock
Helium of the same Chromium version sorts them out:

- --baseline runs every test (or --only's) in stock Helium (HELIUM_BINARY: the helium
  binary of the helium-linux release that linux/helium-linux pins) and writes
  dubna's webextensions/chromium-tests.json: each test's result there, and
  "expected", what passed in each of BASELINE_RUNS runs: the names of its
  runTests() tests, or "*" for a test that passed without them. What passed
  only some of the time, such as a test that races an event, is "flaky": it
  fails the baseline (exit 1) until FIXES removes its race or its entry has a
  "reason".
  Run it again when Chromium moves.
- A run without it checks oganesson (OGANESSON_BINARY, by default the release
  build in work/): what passed in stock Helium has to pass. A test where it
  doesn't is printed as DOWN, with what failed, and the run exits 3, which
  stops a release, until it is fixed or the test's entry in the list gets a
  "reason" for its failure, which --baseline keeps; any other
  exit status but 0 means the run itself failed. --only runs those tests alone.

The run holds the builds lock, the file $BUILDS_LOCK names.
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = ROOT / 'work/chromium-tests'
CHROMIUM = (ROOT / 'helium/chromium_version.txt').read_text().strip()
ARCHIVE = ('https://chromium.googlesource.com/chromium/src/+archive/refs/tags/'
           f'{CHROMIUM}/chrome/test/data/extensions/api_test.tar.gz')
# The api_test/ folders whose tests run: the namespaces the climb touches, and
# the bindings, events and messaging that every API goes through.
NAMESPACES = ['bindings', 'bookmarks', 'browser_action', 'content_scripts', 'context_menus',
              'cookies', 'events', 'executescript', 'extension_action', 'i18n', 'messaging',
              'page_action', 'permissions', 'preference', 'privacy', 'proxy', 'runtime',
              'scripting', 'storage', 'tabs', 'web_navigation', 'web_request', 'windows']
# How many times --baseline runs a test that passes: what passes each time counts.
BASELINE_RUNS = 3
# A test's longest run, from its browser's start to its end.
TIMEOUT = 60
DOWN = 3
os.environ.setdefault('OGANESSON_BINARY',
                      str(ROOT / 'work/helium-linux/build/src/out/Release/oganesson'))
os.environ.setdefault('TMPDIR', str(ROOT / 'work/tmp'))

# Chromium's tests that race on their own, in stock Helium too, with the edit
# (file, old text, new text) that removes the race. A test that turns out
# flaky gets an edit here, or a "reason" in the list, before its baseline.
FIXES = {
    # The test adds its onUpdated listener after tabs.create() resolves, and the
    # new tab's "complete" can come first: the browser sends an event only to a
    # worker with a listener. The listener now comes before the tab.
    'tabs/zoom': [('worker.js', """  const tab = await chrome.tabs.create({url: 'about:blank'});
  chrome.test.assertNoLastError();
  await waitForTabComplete(tab.id);
""", """  const completed = new Set();
  let wake = () => {};
  chrome.tabs.onUpdated.addListener((id, changeInfo) => {
    if (changeInfo.status === 'complete') {
      completed.add(id);
      wake();
    }
  });
  const tab = await chrome.tabs.create({url: 'about:blank'});
  chrome.test.assertNoLastError();
  while (!completed.has(tab.id)) {
    await new Promise(resolve => wake = resolve);
  }
""")],
}

SHIM = """(() => {
  const state = self.__chromiumTest = {result: null, current: null, passing: []};
  const test = chrome.test;
  const notifyPass = test.notifyPass;
  const notifyFail = test.notifyFail;
  const log = test.log;
  // runTests() logs each test's start and its success (test_custom_bindings.js).
  test.log = function(message, ...args) {
    const text = String(message);
    if (text.startsWith('( RUN      ) ')) {
      state.current = text.slice(13);
    } else if (text.startsWith('(  SUCCESS )') && state.current) {
      state.passing.push(state.current);
      state.current = null;
    } else if (text.startsWith('(  FAILED  )')) {
      state.current = null;
    }
    return log.call(this, message, ...args);
  };
  test.notifyPass = function(...args) {
    state.result = state.result || 'pass';
    return notifyPass.apply(this, args);
  };
  test.notifyFail = function(message, ...args) {
    state.result = state.result || 'fail: ' + message;
    return notifyFail.call(this, message, ...args);
  };
  test.getConfig = callback => {
    const config = %s;
    return callback ? callback(config) : Promise.resolve(config);
  };
})();
"""


def strip_comments(text):
    """Chromium's manifests may have // and /* */ comments."""
    return re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', lambda m: m.group(1) or '',
                  text, flags=re.S)


def fetch_tests():
    """The api_test/ folder of CHROMIUM, downloaded once."""
    folder = CACHE / CHROMIUM / 'api_test'
    if not folder.is_dir():
        with urllib.request.urlopen(ARCHIVE, timeout=300) as response:
            data = response.read()
        partial = folder.with_name('api_test.partial')
        shutil.rmtree(partial, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(partial, filter='data')
        partial.rename(folder)
    return folder


def read_manifest(folder):
    try:
        manifest = json.loads(strip_comments((folder / 'manifest.json').read_text()))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def test_pages(folder):
    """The pages of an extension without a background that run tests: each
    .html file whose scripts call chrome.test, outside the folders of other
    extensions."""
    pages = []
    for html in sorted(folder.rglob('*.html')):
        if any((parent / 'manifest.json').exists()
               for parent in html.parents if parent != folder and folder in parent.parents):
            continue
        sources = re.findall(r'<script[^>]+src="([^"]+)"', html.read_text(errors='replace'))
        scripts = [html.parent / source for source in sources if '://' not in source]
        texts = [html.read_text(errors='replace')] + [s.read_text(errors='replace')
                                                     for s in scripts if s.is_file()]
        if any('chrome.test.' in text for text in texts):
            pages.append(html.relative_to(folder).as_posix())
    return pages


def find_tests(api_test):
    """Each test's name: an extension's folder relative to api_test/, and for
    one without a background, ":" and the test page."""
    names = []
    for namespace in NAMESPACES:
        for manifest in sorted((api_test / namespace).rglob('manifest.json')):
            folder = manifest.parent
            found = read_manifest(folder)
            if not found:
                continue
            name = folder.relative_to(api_test).as_posix()
            if found.get('background'):
                names.append(name)
            else:
                names += [f'{name}:{page}' for page in test_pages(folder)]
    return names


def prepare(source, target, port, page, fixes=()):
    """The test in `source` copied to `target`, with `fixes` (FIXES) made and
    the shim running first in its background or in `page`."""
    shutil.copytree(source, target)
    for file, old, new in fixes:
        text = (target / file).read_text()
        if text.count(old) != 1:
            raise ValueError(f'FIXES of {source.name}: {file} changed upstream')
        (target / file).write_text(text.replace(old, new))
    (target / '__shim.js').write_text(SHIM % json.dumps(
        {'testServer': {'port': port}, 'testDataDirectory': f'http://localhost:{port}/extensions'}))
    manifest = read_manifest(target)
    background = manifest.get('background') or {}
    if background.get('service_worker'):
        worker = background['service_worker'].lstrip('/')
        if background.get('type') == 'module':
            (target / '__worker.js').write_text(f"import '/__shim.js';\nimport '/{worker}';\n")
        else:
            (target / '__worker.js').write_text(f"importScripts('/__shim.js', '/{worker}');\n")
        background['service_worker'] = '__worker.js'
    elif background.get('scripts'):
        background['scripts'] = ['__shim.js', *background['scripts']]
    else:
        html = target / (page or background['page'].lstrip('/'))
        html.write_text('<script src="/__shim.js"></script>\n' + html.read_text(errors='replace'))
    (target / 'manifest.json').write_text(json.dumps(manifest))


def run_test(name, api_test, port):
    """The test's result, 'pass' or 'fail: <message>' or why it didn't end,
    and the names of its runTests() tests that passed."""
    from harness import Browser, Page, extension_id, wait_for  # pylint: disable=import-outside-toplevel
    folder = Path(tempfile.mkdtemp(prefix='chromium-test-')) / 'extension'
    source, _, page_path = name.partition(':')
    browser = None
    try:
        prepare(api_test / source, folder, port, page_path, FIXES.get(source, ()))
        # chrome.test is only there with --test-type (feature_cache.cc).
        browser = Browser(args=('--test-type', f'--load-extension={folder}',
                                f'--host-resolver-rules=MAP * 127.0.0.1:{port}'))
        extension = extension_id(folder)
        if page_path:
            browser.new_tab(f'chrome-extension://{extension}/{page_path}')
            target = wait_for(lambda: next((t for t in browser.targets()
                                            if t['url'].startswith(f'chrome-extension://{extension}/')
                                            and t['type'] == 'page'), None),
                              timeout=TIMEOUT, what='the test page')
            page = Page(target)
        else:
            page = browser.extension_background(extension, timeout=TIMEOUT)
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            state = page.eval('self.__chromiumTest', gesture=False)
            if state and state['result']:
                return {'result': state['result'], 'passing': state['passing']}
            time.sleep(0.2)
        return {'result': 'timeout: no notifyPass() or notifyFail()',
                'passing': state['passing'] if state else []}
    except Exception as error:  # pylint: disable=broad-except
        return {'result': f'error: {type(error).__name__}: {error}'.splitlines()[0][:300],
                'passing': []}
    finally:
        if browser:
            browser.stop()
        shutil.rmtree(folder.parent, ignore_errors=True)


def expected(run):
    """What passed: the runTests() tests, or the whole test ("*") for one that
    passed without them."""
    if run['passing']:
        return sorted(set(run['passing']))
    return ['*'] if run['result'] == 'pass' else []


def missing(baseline, name, run):
    """What passed in stock Helium and didn't in `run`."""
    return sorted(set(baseline['tests'][name]['expected']) - set(expected(run)))


def serve(api_test):
    """A server of api_test/ under /extensions/api_test/, for every host."""
    from harness import Server  # pylint: disable=import-outside-toplevel
    routes = {}
    for path in api_test.rglob('*'):
        if path.is_file():
            kind = {'.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
                    '.css': 'text/css'}.get(path.suffix, 'application/octet-stream')
            routes[f'/extensions/api_test/{path.relative_to(api_test).as_posix()}'] = (
                200, {'Content-Type': kind}, path.read_bytes())
    return Server(routes)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='the tests to run, comma-separated')
    parser.add_argument('--baseline', action='store_true',
                        help="run in stock Helium and write dubna's chromium-tests.json")
    parser.add_argument('--dubna', type=Path, default=ROOT / 'dubna')
    parser.add_argument('-j', '--jobs', type=int, default=max(1, min(8, os.cpu_count() // 4)))
    args = parser.parse_args()
    listing = args.dubna / 'webextensions/chromium-tests.json'
    if args.baseline:
        os.environ['OGANESSON_BINARY'] = os.environ.get('HELIUM_BINARY', '')
        if not os.environ['OGANESSON_BINARY']:
            sys.exit('set HELIUM_BINARY to stock Helium of Chromium ' + CHROMIUM)
    api_test = fetch_tests()
    names = find_tests(api_test)
    if not args.baseline:
        baseline = json.loads(listing.read_text())
        if baseline['chromium'] != CHROMIUM:
            sys.exit(f"{listing} is of Chromium {baseline['chromium']}, oganesson builds "
                     f'{CHROMIUM}: run --baseline')
        names = [name for name in names if baseline['tests'].get(name, {}).get('expected')]
    if args.only:
        only = args.only.split(',')
        unknown = set(only) - set(names)
        if unknown:
            sys.exit(f'not a test that passes in stock Helium: {sorted(unknown)}')
        names = only
    from corpus import hold_builds_lock  # pylint: disable=import-outside-toplevel
    lock = hold_builds_lock()  # noqa: F841 (held until exit)
    server = serve(api_test)
    start = time.monotonic()
    try:
        with ThreadPoolExecutor(args.jobs) as pool:
            def run_all(tests):
                return dict(zip(tests, pool.map(
                    lambda name: run_test(name, api_test, server.port), tests)))
            results = run_all(names)
            if args.baseline:
                # A test whose result depends on timing would stop releases at random:
                # only what passes every time counts, and the rest is "flaky".
                for name in names:
                    results[name]['ever'] = set(expected(results[name]))
                for _ in range(BASELINE_RUNS - 1):
                    again = run_all([name for name in names if results[name]['ever']])
                    for name, run in again.items():
                        results[name]['ever'] |= set(expected(run))
                        results[name]['passing'] = sorted(
                            set(expected(results[name])) & set(expected(run)))
                        if run['result'] != 'pass':
                            results[name]['result'] = run['result']
    finally:
        server.stop()
    minutes = (time.monotonic() - start) / 60
    if args.baseline:
        old = json.loads(listing.read_text())['tests'] if listing.is_file() else {}
        tests = dict(old) if args.only else {}
        for name, run in results.items():
            tests[name] = {'helium': run['result'], 'expected': expected(run)}
            flaky = sorted(run['ever'] - set(expected(run)))
            if flaky:
                tests[name]['flaky'] = flaky
            if old.get(name, {}).get('reason'):
                tests[name]['reason'] = old[name]['reason']
        listing.write_text(json.dumps({'chromium': CHROMIUM, 'tests': tests}, indent=1,
                                      sort_keys=True) + '\n')
        count = sum(len(test['expected']) for test in tests.values())
        print(f'{listing}: {count} tests of {len(tests)} test extensions pass in stock Helium, '
              f'{BASELINE_RUNS} times ({minutes:.1f} min)')
        flaky = {name: test['flaky'] for name, test in tests.items()
                 if test.get('flaky') and not test.get('reason')}
        for name, lost in sorted(flaky.items()):
            print(f"FLAKY {name}: {', '.join(lost)}: fix it in FIXES, or give it a reason")
        return 1 if flaky else 0
    for name in results:
        if baseline['tests'][name].get('reason'):
            print(f"known {name}: {baseline['tests'][name]['reason']}")
    down = {name: (missing(baseline, name, run), run['result'])
            for name, run in results.items()
            if missing(baseline, name, run) and not baseline['tests'][name].get('reason')}
    for name, (lost, result) in sorted(down.items()):
        print(f"DOWN {name}: {', '.join(lost)}: {result}")
    count = sum(len(baseline['tests'][name]['expected']) for name in results)
    print(f"{count - sum(len(lost) for lost, _ in down.values())} of {count} tests that pass in "
          f'stock Helium pass ({minutes:.1f} min)')
    return DOWN if down else 0


if __name__ == '__main__':
    sys.exit(main())
