#!/usr/bin/env python3
"""The WebExtensions climb's test score (dubna's webextensions/README.md,
"Test score"): Firefox's own WebExtensions tests, ported to this harness, run
in oganesson.

  firefox_tests.py [--only PORT[,PORT...]] [--dubna DIR]

It runs the port (`port` in dubna's webextensions/firefox-tests.json, a file
in firefox/ made with extension_test_utils.py) of each test file whose state
is `ported`, each port in a process and a browser of its own. A port passes
when all its tests pass.

A full run writes <dubna>/webextensions/score/oganesson-firefox-tests.json:
the date, the browser's version, how many ported files pass, how many are
ported, how many files there are that aren't `n/a`, and each ported file's
result with its first failure and the tests that pass. With --only (ports'
file names, such as firefox/test_ext_scripting_mv2.py), it runs those,
prints each one's result next to the committed score's, writes nothing, and
exits 1 when a test that passed then doesn't pass now.

The run holds the builds lock ($BUILDS_LOCK, by default ~/dev/.builds.lock),
and runs the browser from OGANESSON_BINARY, by default the release build in
work/.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ.setdefault('OGANESSON_BINARY',
                      str(ROOT / 'work/helium-linux/build/src/out/Release/oganesson'))
os.environ.setdefault('TMPDIR', str(ROOT / 'work/tmp'))
# pylint: disable=wrong-import-position
from corpus import hold_builds_lock, version  # noqa: E402
from harness import BINARY  # noqa: E402

# A port's slowest run, with its browser's start and stop.
TIMEOUT = 600
# The longest failure a score keeps.
ERROR_LENGTH = 300


def first_failure(output):
    """The first failure's message in unittest's output: the line after the
    traceback that the first FAIL or ERROR block ends with."""
    blocks = re.split(r'^={70}$', output, flags=re.M)[1:]
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        trace = next((i for i, line in enumerate(lines) if line.startswith('Traceback')), None)
        if trace is not None:
            message = next((line for line in lines[trace + 1:] if not line.startswith(' ')), '')
            return f'{lines[0].strip()}: {message.strip()}'[:ERROR_LENGTH]
    return output.strip().splitlines()[-1][:ERROR_LENGTH] if output.strip() else 'no output'


def failed_tests(output):
    """The tests that failed or errored, from the headers of unittest's
    failure blocks: a test's own "... FAIL" line may have other output in it."""
    return sorted(set(re.findall(r'^(?:FAIL|ERROR): (test_\w+) \(', output, re.M)))


def test_names(module):
    """The names of the module's tests, without running them."""
    names = []
    pending = [unittest.defaultTestLoader.loadTestsFromName(module)]
    while pending:
        for test in pending.pop():
            if isinstance(test, unittest.TestSuite):
                pending.append(test)
            else:
                names.append(test.id().rsplit('.', 1)[-1])
    return sorted(names)


def run_port(port):
    """Whether the port passes, its first failure, and its tests that pass."""
    module = port.removesuffix('.py').replace('/', '.')
    try:
        done = subprocess.run([sys.executable, '-m', 'unittest', '-v', module], cwd=HERE,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return False, f'timed out after {TIMEOUT}s', []
    if done.returncode == 0:
        return True, None, test_names(module)
    failed = failed_tests(done.stdout)
    # A failure outside the tests (setUpClass) fails them all.
    passing = [name for name in test_names(module) if name not in failed] if failed else []
    return False, first_failure(done.stdout), passing


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='the ports to run, comma-separated')
    parser.add_argument('--dubna', type=Path, default=ROOT / 'dubna',
                        help='the dubna checkout: its firefox-tests.json, and the score it gets')
    args = parser.parse_args()
    if not BINARY.is_file():
        sys.exit(f'no browser binary at {BINARY}; run ./oganesson.py build --release')
    tests = json.loads((args.dubna / 'webextensions/firefox-tests.json').read_text())['tests']
    ported = [t for t in tests if t['state'] == 'ported']
    if args.only:
        only = set(args.only.split(','))
        ported = [t for t in ported if t['port'] in only]
        if len(ported) != len(only):
            sys.exit(f"not ported: {only - {t['port'] for t in ported}}")
    missing = [t['port'] for t in ported if not (HERE / t['port']).is_file()]
    if missing:
        sys.exit(f'ports missing from {HERE}: {missing}')
    score_path = args.dubna / 'webextensions/score/oganesson-firefox-tests.json'
    lock = hold_builds_lock()  # noqa: F841 (held until exit)
    results = {}
    for number, test in enumerate(ported, 1):
        passed, error, passing = run_port(test['port'])
        results[test['path']] = {'port': test['port'], 'passed': passed, 'error': error,
                                 'passing': passing}
        print(f"{number}/{len(ported)} {'pass' if passed else 'FAIL'} {test['port']}"
              f"{'  ' + error if error else ''}", flush=True)
    if args.only:
        old = json.loads(score_path.read_text())['tests'] if score_path.is_file() else {}
        down = False
        for path, result in results.items():
            before = old.get(path)
            # A test that passed in the committed score and doesn't now.
            new = sorted(set(before.get('passing', [])) - set(result['passing'])) if before else []
            down = down or bool(new)
            print(f"{result['port']}: {before['passed'] if before else '-'} -> {result['passed']}"
                  f"{'  DOWN: ' + ', '.join(new) if new else ''}")
        return 1 if down else 0
    score = {
        'date': datetime.date.today().isoformat(),
        'browser': version(),
        'passing': sum(1 for r in results.values() if r['passed']),
        'ported': len(results),
        'total': sum(1 for t in tests if t['state'] != 'n/a'),
        'tests': results,
    }
    score_path.parent.mkdir(exist_ok=True)
    score_path.write_text(json.dumps(score, indent=1, ensure_ascii=False) + '\n')
    print(f"{score_path}: {score['passing']} of {score['ported']} ported files pass, "
          f"of {score['total']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
