#!/usr/bin/env python3
"""The WebExtensions climb's corpus runner (dubna's webextensions/README.md):
the level each add-on of dubna's webextensions/corpus.json reaches in
oganesson.

  corpus.py [--only ID[,ID...]] [--dubna DIR] [--cache DIR]

Each add-on gets the highest level it passes:

L0  Chromium reads its manifest: loading fails, if it does, past that.
L1  It installs, unpacked with --load-extension (until the .xpi install step
    ships).
L2  Its background page or service worker starts, if it has one, and nothing
    names a missing API or manifest key: its manifest has no key that Firefox
    reads (FIREFOX_KEYS) and no permission that the feature files of the
    build's tree (_manifest_features.json, _permission_features.json) and its
    permission aliases (ALIASES, such as Firefox's "menus" for "contextMenus")
    leave out, and it throws no uncaught error in its first seconds. Such
    an error nearly always comes from an API that isn't there. Any uncaught
    error counts, so the score errs low, but for RACES, errors whose timing
    varies between runs. Chromium's own warnings for unknown
    keys don't reach chrome://extensions here, hence the feature files.

A full run writes <dubna>/webextensions/score/oganesson.json: the date, the
browser's version, how many add-ons reach each level (or a higher one), and
each add-on's level and the first error that kept it from the next one. With
--only, it runs those add-ons, prints each one's level next to the committed
score's, writes nothing, and exits 1 when one went down a level.

The add-ons load in groups of GROUP to a browser start, so one bad add-on
doesn't stop the run. The run holds the builds lock ($BUILDS_LOCK, by default
~/dev/.builds.lock). It reads the .xpi files from the cache of dubna's
`tools/amo_corpus.py fetch`, and the browser from OGANESSON_BINARY, by default
the release build in work/.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('OGANESSON_BINARY',
                      str(ROOT / 'work/helium-linux/build/src/out/Release/oganesson'))
os.environ.setdefault('TMPDIR', str(ROOT / 'work/tmp'))
# pylint: disable=wrong-import-position
from harness import BINARY, DEVELOPER_MODE, Browser, extension_id, unpack_xpi, wait_for

LEVELS = ('L0', 'L1', 'L2')
GROUP = 20
# The manifest keys that Firefox reads (MDN's manifest.json keys that Firefox
# supports, and experiment_apis from Firefox's schemas), less its metadata,
# which no add-on needs Chromium to read. Firefox does nothing with other keys:
# it warns about an unknown one, such as a "//1" comment, and accepts
# minimum_opera_version without using it. So they don't count.
FIREFOX_KEYS = (
    'action', 'author', 'background', 'browser_action', 'chrome_settings_overrides',
    'chrome_url_overrides', 'commands', 'content_scripts', 'content_security_policy',
    'dark_theme', 'declarative_net_request', 'default_locale', 'description', 'devtools_page',
    'dictionaries', 'experiment_apis', 'homepage_url', 'host_permissions', 'icons',
    'incognito', 'manifest_version', 'name', 'omnibox', 'optional_host_permissions',
    'optional_permissions', 'options_page', 'options_ui', 'page_action', 'permissions',
    'protocol_handlers', 'sandbox', 'short_name', 'sidebar_action', 'theme',
    'theme_experiment', 'user_scripts', 'version', 'web_accessible_resources',
)
# The build's tree, with the feature files.
TREE = BINARY.parents[2]
FEATURES = ('chrome/common/extensions/api/_{}_features.json',
            'extensions/common/api/_{}_features.json')
# Where Chromium names other names for permissions: Alias("alias", "name").
ALIASES = ('chrome/common/extensions/permissions/chrome_api_permissions.cc',
           'extensions/common/permissions/extensions_api_permissions.cc')
# How long the add-ons of a group get to start their backgrounds, and then
# to report errors from their start.
START = 10
SETTLE = 2
# The longest error a score keeps.
ERROR_LENGTH = 300
UNREADABLE = ('Manifest file is missing or unreadable', 'Manifest is not valid JSON')
# Uncaught errors that name no missing API and come and go between runs: a
# message sent at the start before the page that listens for it is up, a
# reply whose page went away before it answered, and a tab gone by the time
# the add-on asks for it (the runner's own tabs).
RACES = ('Receiving end does not exist', 'message channel closed before a response',
         'No tab with id')


def feature_file(path):
    """A feature file: JSON with // comments."""
    text = path.read_text()
    kept, in_string, i = [], False, 0
    while i < len(text):
        char = text[i]
        if in_string and char == '\\':
            kept.append(text[i:i + 2])
            i += 2
            continue
        if char == '"':
            in_string = not in_string
        elif not in_string and text.startswith('//', i):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            continue
        kept.append(char)
        i += 1
    return json.loads(''.join(kept))


def known(kind):
    """The names Chromium has for `kind`: 'manifest', the top-level keys of a
    manifest, or 'permission', the permissions (some dotted, as
    downloads.open)."""
    names = set()
    for pattern in FEATURES:
        for name in feature_file(TREE / pattern.format(kind)):
            names.add(name.split('.')[0] if kind == 'manifest' else name)
    if kind == 'permission':
        for path in ALIASES:
            text = (TREE / path).read_text()
            for alias, name in re.findall(r'Alias\("([^"]+)", "([^"]+)"\)', text):
                if name in names:
                    names.add(alias)
    return names


def unknown(manifest, keys, permissions):
    """What `manifest` asks for that isn't among `keys` and `permissions`."""
    found = [f"unknown manifest key '{key}'" for key in manifest
             if key in FIREFOX_KEYS and key not in keys]
    for listed in ('permissions', 'optional_permissions'):
        for name in manifest.get(listed) or []:
            if (isinstance(name, str) and '://' not in name and name != '<all_urls>'
                    and name not in permissions):
                found.append(f"unknown permission '{name}'")
    return found


def level(load_error, installed, background, missing, uncaught):
    """The level and the error that kept it from the next one, from what the
    browser showed: `load_error`, Chromium's error for a failed load, or None;
    `installed`, whether the add-on is installed; `background`, whether its
    background started (None: it has none); `missing`, what its manifest asks
    for that Chromium doesn't know (unknown()); `uncaught`, its uncaught
    errors."""
    if load_error and any(text in load_error for text in UNREADABLE):
        return None, load_error
    if not installed:
        return 'L0', load_error or 'not installed'
    if background is False:
        return 'L1', uncaught[0] if uncaught else 'the background did not start'
    named = missing + uncaught
    if named:
        return 'L1', named[0]
    return 'L2', None


def read_manifest(folder):
    """The add-on's manifest, or {} when it doesn't parse."""
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def console_message(line):
    """A console line of browser.log, as `"<message>", source: <url> (<line>)`,
    as the message and the file and line it came from."""
    found = re.search(r'"(.*)", source: chrome-extension://[^/]+/(\S*) \((\d+)\)', line)
    return f'{found[1]} ({found[2]}:{found[3]})' if found else line.split('CONSOLE', 1)[1]


def run_group(items, xpis, work):
    """Loads the add-ons `items` (corpus entries) from their .xpi files
    `xpis` in one browser and returns {id: (level, error)}."""
    folders = {}
    for item, xpi in zip(items, xpis):
        folder = work / item['sha256']
        try:
            folders[item['id']] = unpack_xpi(xpi, folder)
        except Exception as error:  # pylint: disable=broad-except
            folders[item['id']] = None
            print(f"{item['id']}: {error}", file=sys.stderr)
    loadable = [f for f in folders.values() if f]
    results = {i: (None, 'the .xpi does not unpack') for i, f in folders.items() if not f}
    if not loadable:
        return results
    # --noerrdialogs: a failed load would hold the start with a message box.
    keys, permissions = known('manifest'), known('permission')
    browser = Browser(args=['--noerrdialogs',
                            f"--load-extension={','.join(str(f) for f in loadable)}"],
                      prefs=DEVELOPER_MODE)
    try:
        ids = {i: extension_id(f) for i, f in folders.items() if f}
        manifests = {i: read_manifest(f) for i, f in folders.items() if f}
        expected = {ids[i] for i, m in manifests.items() if m.get('background')}
        # Every background that will start, or the end of START. One seen once
        # counts: an add-on may remove itself after its start.
        started = set()
        deadline = time.monotonic() + START
        while time.monotonic() < deadline:
            started |= {t['url'].split('/')[2] for t in browser.targets()
                       if t['type'] in ('background_page', 'service_worker')
                       and t['url'].startswith('chrome-extension://')}
            if expected <= started:
                break
            time.sleep(0.5)
        time.sleep(SETTLE)
        page = browser.new_tab('chrome://extensions')
        try:
            # The new tab is blank until the page commits, without the API.
            wait_for(lambda: page.eval('!!chrome.developerPrivate'), what='chrome://extensions')
            installed = {e['id']: e for e in page.eval(
                'new Promise(r => chrome.developerPrivate.getExtensionsInfo('
                '{includeDisabled: true, includeTerminated: true}, r))')}
        finally:
            browser.close_target(page)
        log = browser.log_path.read_text(errors='replace')
        for item_id, folder in folders.items():
            if not folder:
                continue
            extension = ids[item_id]
            # "Failed to load extension from: <the folder's real path>. <error>"
            prefix = f'{folder.resolve()}. '
            load_error = next((line.split(prefix, 1)[1] for line in log.splitlines()
                               if 'Extension error: ' in line and prefix in line), None)
            info = installed.get(extension)
            # Its own console lines: another add-on's error may name this
            # one's page in its message ("Cannot access contents of url").
            uncaught = [console_message(line) for line in log.splitlines()
                        if 'CONSOLE' in line
                        and f'", source: chrome-extension://{extension}/' in line
                        and 'Uncaught' in line and not any(race in line for race in RACES)]
            if info:
                uncaught += [e['message'] for e in info.get('runtimeErrors', [])
                             if 'Uncaught' in e['message']
                             and not any(race in e['message'] for race in RACES)]
            background = (extension in started) if manifests[item_id].get('background') else None
            # An add-on whose background started was installed, even when it
            # is gone by now: some remove themselves (management.uninstallSelf).
            found, error = level(load_error, bool(info) or extension in started, background,
                                 unknown(manifests[item_id], keys, permissions), uncaught)
            results[item_id] = (found, error and error[:ERROR_LENGTH])
    finally:
        browser.stop()
    return results


def run_safely(items, xpis, work):
    """run_group(), and when the browser fails with a group, each add-on of it
    alone: one that the browser still fails with gets L0 and the failure."""
    try:
        return run_group(items, xpis, work)
    except Exception as error:  # pylint: disable=broad-except
        if len(items) == 1:
            return {items[0]['id']: ('L0', f'the browser failed: {error}'[:ERROR_LENGTH])}
    results = {}
    for number, (item, xpi) in enumerate(zip(items, xpis)):
        results.update(run_safely([item], [xpi], work / f'alone-{number}'))
    return results


def version():
    out = subprocess.run([str(BINARY), '--version'], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def at_least(found, name):
    return found is not None and LEVELS.index(found) >= LEVELS.index(name)


def hold_builds_lock():
    lock = open(os.environ.get('BUILDS_LOCK', Path.home() / 'dev/.builds.lock'), 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('corpus.py: waiting for the builds lock', file=sys.stderr, flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
    return lock  # held until the process exits


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='the Gecko IDs of the add-ons to run, comma-separated')
    parser.add_argument('--dubna', type=Path, default=ROOT / 'dubna',
                        help='the dubna checkout: its corpus.json, and the score it gets')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/dubna-amo-corpus',
                        help='the .xpi files of amo_corpus.py fetch')
    args = parser.parse_args()
    if not BINARY.is_file():
        sys.exit(f'no browser binary at {BINARY}; run ./oganesson.py build --release')
    corpus = json.loads((args.dubna / 'webextensions/corpus.json').read_text())
    score_path = args.dubna / 'webextensions/score/oganesson.json'
    if args.only:
        only = set(args.only.split(','))
        corpus = [item for item in corpus if item['id'] in only]
        if len(corpus) != len(only):
            sys.exit(f"not in the corpus: {only - {item['id'] for item in corpus}}")
    xpis = [args.cache / f"{item['sha256']}.xpi" for item in corpus]
    absent = [x for x in xpis if not x.is_file()]
    if absent:
        sys.exit(f'{len(absent)} .xpi files are not in {args.cache}; '
                 'run dubna/tools/amo_corpus.py fetch')
    lock = hold_builds_lock()  # noqa: F841 (held until exit)
    results = {}
    with tempfile.TemporaryDirectory(prefix='oganesson-corpus-') as work:
        for start in range(0, len(corpus), GROUP):
            items = corpus[start:start + GROUP]
            results.update(run_safely(items, xpis[start:start + GROUP],
                                      Path(work) / str(start)))
            done = sum(1 for r in results.values() if r[0] == 'L2')
            print(f'{len(results)} of {len(corpus)} add-ons, {done} at L2', flush=True)
    addons = {item['id']: {'level': results[item['id']][0], 'error': results[item['id']][1]}
              for item in corpus}
    if args.only:
        old = json.loads(score_path.read_text())['addons'] if score_path.is_file() else {}
        down = False
        for item_id, result in addons.items():
            before = old.get(item_id, {}).get('level')
            went_down = at_least(before, 'L0') and not at_least(result['level'], before)
            down = down or went_down
            print(f"{item_id}: {before or '-'} -> {result['level'] or '-'}"
                  f"{'  DOWN' if went_down else ''}  {result['error'] or ''}")
        return 1 if down else 0
    score = {
        'date': datetime.date.today().isoformat(),
        'browser': version(),
        'levels': {name: sum(1 for a in addons.values() if at_least(a['level'], name))
                   for name in LEVELS},
        'addons': addons,
    }
    score_path.parent.mkdir(exist_ok=True)
    score_path.write_text(json.dumps(score, indent=1, ensure_ascii=False) + '\n')
    print(f"{score_path}: {', '.join(f'{k} {v}' for k, v in score['levels'].items())}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
