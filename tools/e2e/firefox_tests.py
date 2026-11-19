#!/usr/bin/env python3
"""The WebExtensions climb's test score (dubna's webextensions/README.md,
"Test score"): Firefox's own WebExtensions tests, ported to this harness, run
in oganesson.

  firefox_tests.py [--only PORT[,PORT...]] [--dubna DIR] [--jobs N]

It runs the port (`port` in dubna's webextensions/firefox-tests.json, a file
in firefox/ made with extension_test_utils.py) of each test file whose state
is `ported`, each port in a process and a browser of its own, --jobs of
them at a time (by default as `./oganesson.py test` does: a quarter of the
CPUs, at most 8). A port passes when all its tests pass.

A full run writes <dubna>/webextensions/score/oganesson-firefox-tests.json:
the date, the browser's version, how many ported files pass, how many are
ported, how many files there are that aren't `n/a`, and each ported file's
result with its first failure and the tests that pass. With --only (ports'
file names, such as firefox/test_ext_scripting_mv2.py), it runs those and
writes nothing. Either way it prints each port's result next to the
committed score's (HEAD of the --dubna tree, so a rerun compares with the
same score), then each of its tests, pass or FAIL. It exits 3 when a test
that passed then and still exists doesn't pass now (DOWN), and keeps the
profiles and logs of that port's failed tests (OGANESSON_E2E_KEEP=1 keeps
every port's); any other exit status but 0 means the run itself failed.

A port that the list sets `ported` only in a dubna worktree runs with
--dubna pointing there.

The run holds the builds lock ($BUILDS_LOCK, by default ~/dev/.builds.lock),
and runs the browser from OGANESSON_BINARY, by default the release build in
work/.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ.setdefault('OGANESSON_BINARY',
                      str(ROOT / 'work/helium-linux/build/src/out/Release/oganesson'))
os.environ.setdefault('TMPDIR', str(ROOT / 'work/tmp'))
# pylint: disable=wrong-import-position
from corpus import hold_builds_lock, version  # noqa: E402
from harness import BINARY, KEEP  # noqa: E402

# A port's slowest run, with its browser's start and stop.
TIMEOUT = 600
# The longest failure a score keeps.
ERROR_LENGTH = 300
# The exit status for a drop; 1 is any other failure of the run.
DOWN = 3
# The ports' processes that run now, for an interrupt to stop.
RUNNING = set()


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


def committed_score(dubna, score_path):
    """The ported tests' results in the score committed in the dubna tree
    (its HEAD), which no run overwrites; the file itself when the tree isn't
    a Git checkout."""
    relative = score_path.relative_to(dubna).as_posix()
    # Git's messages in English, which the check below reads.
    shown = subprocess.run(['git', '-C', str(dubna), 'show', f'HEAD:{relative}'],
                           capture_output=True, text=True, check=False,
                           env=dict(os.environ, LC_ALL='C', LANGUAGE='C'))
    if shown.returncode == 0:
        return json.loads(shown.stdout)['tests']
    if not (dubna / '.git').exists():
        return json.loads(score_path.read_text())['tests'] if score_path.is_file() else {}
    # Not committed yet: nothing to compare with. Any other failure (an
    # unsafe owner, a broken worktree) would hide every drop, so it stops.
    if re.search(r"does not exist in 'HEAD'|but not in 'HEAD'|invalid object name 'HEAD'",
                 shown.stderr):
        return {}
    sys.exit(f'firefox_tests.py: no committed score in {dubna}: {shown.stderr.strip()}')


def run_port(port):
    """Whether the port passes, its first failure, its tests that pass, and
    the folders its browsers kept (harness.py's "kept <root>" lines: a failed
    test's profile and log)."""
    module = port.removesuffix('.py').replace('/', '.')
    with subprocess.Popen([sys.executable, '-m', 'unittest', '-v', module], cwd=HERE,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as child:
        RUNNING.add(child)
        try:
            output = child.communicate(timeout=TIMEOUT)[0]
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            # Killed: its browsers' folders stay in TMPDIR, unnamed.
            return False, f'timed out after {TIMEOUT}s', [], []
        finally:
            RUNNING.discard(child)
    kept = [Path(root) for root in re.findall(r'^ +kept (\S+) \(log: ', output, re.M)]
    if child.returncode == 0:
        return True, None, test_names(module), kept
    failed = failed_tests(output)
    # A failure outside the tests (a setUpClass of any of the port's
    # classes, whose tests then don't run) fails them all.
    outside = re.search(r'^(?:FAIL|ERROR): (?!test_)\w+ \(', output, re.M)
    passing = ([name for name in test_names(module) if name not in failed]
               if failed and not outside else [])
    return False, first_failure(output), passing, kept


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='the ports to run, comma-separated')
    parser.add_argument('--dubna', type=Path, default=ROOT / 'dubna',
                        help='the dubna checkout: its firefox-tests.json, and the score it gets')
    parser.add_argument('-j', '--jobs', type=int, default=max(1, min(8, os.cpu_count() // 4)),
                        help='how many ports run at once')
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
    # Read first: a run that can't compare stops before it starts.
    old = committed_score(args.dubna, score_path)
    lock = hold_builds_lock()  # noqa: F841 (held until exit)
    results = {}
    # The folders that failed tests kept go unless their port has a drop (or
    # OGANESSON_E2E_KEEP=1): most failures are known gaps.
    kept = {}
    try:
        return compare(ported, results, kept, old, args, tests, score_path)
    except BaseException:
        for roots in kept.values():
            for root in roots:
                if root.exists():
                    print(f'  left {root}', file=sys.stderr)
        raise


def compare(ported, results, kept, old, args, tests, score_path):
    """Runs the ports, prints each one's result next to the committed
    score's, and writes the score unless --only; the exit status."""
    with ThreadPoolExecutor(args.jobs) as pool:
        try:
            # map() gives the results in the list's order, each once it is done.
            runs = pool.map(run_port, [test['port'] for test in ported])
            for number, (test, run) in enumerate(zip(ported, runs), 1):
                passed, error, passing, kept[test['path']] = run
                results[test['path']] = {'port': test['port'], 'passed': passed,
                                         'error': error, 'passing': passing}
                print(f"{number}/{len(ported)} {'pass' if passed else 'FAIL'} {test['port']}"
                      f"{'  ' + error if error else ''}", flush=True)
        except BaseException:
            # An interrupt (harness.py makes SIGTERM one) reaches this thread
            # alone: stop the running ports, or the pool waits for them with
            # the builds lock held.
            pool.shutdown(wait=False, cancel_futures=True)
            for child in list(RUNNING):
                child.terminate()
            raise
    down = False
    for path, result in results.items():
        before = old.get(path)
        names = test_names(result['port'].removesuffix('.py').replace('/', '.'))
        # A test that passed in the score before this run, still exists, and
        # doesn't pass now: a renamed or removed test isn't a drop.
        new = sorted((set(before.get('passing', [])) & set(names)) - set(result['passing'])
                     if before else [])
        down = down or bool(new)
        print(f"{result['port']}: {before['passed'] if before else '-'} -> {result['passed']}"
              f"{'  DOWN: ' + ', '.join(new) if new else ''}")
        for root in kept[path]:
            if new or KEEP:
                print(f'  kept {root}')
            else:
                shutil.rmtree(root, ignore_errors=True)
                if root.exists():  # A browser that outlived its port wrote on.
                    print(f'  could not remove {root}')
        for name in names:
            print(f"  {'pass' if name in result['passing'] else 'FAIL'} {name}")
    if args.only:
        return DOWN if down else 0
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
    return DOWN if down else 0


if __name__ == '__main__':
    sys.exit(main())
