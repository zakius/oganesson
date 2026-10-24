"""Runs the browser test classes, `--jobs` of them at a time, each in a
process of its own; `./oganesson.py test` calls it. Every class already has
its own X display, browser, profile and ports, so classes don't share
anything but the machine. A class's tests run in order in its process, as
numbered steps need.

With --jobs 1 it is a plain unittest run, one class after another, with
unittest's output as it happens. Otherwise each class's output comes whole
as it ends, then a summary. With --repeat N each class runs N times, and the
summary lists every test that didn't pass every run.

    python3 run.py [--jobs N] [--repeat N] [-k PATTERN]... [test_module]...
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).parent
# Each class's time in the last run that had it, to start long classes first.
TIMES = Path(tempfile.gettempdir()) / 'oganesson-e2e-times.json'


def classes(modules, patterns):
    """'module.Class' of each class with tests selected, with its test count,
    in the order unittest would run them."""
    loader = unittest.TestLoader()
    # As unittest's -k: a pattern without a wildcard matches a substring.
    loader.testNamePatterns = [p if '*' in p else f'*{p}*' for p in patterns] or None
    sys.path.insert(0, str(HERE))
    suite = loader.loadTestsFromNames(modules) if modules else loader.discover(str(HERE), 'test_*.py')
    found = {}

    def walk(suite):
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                walk(test)
            else:
                name = test.id().rsplit('.', 1)[0]
                found[name] = found.get(name, 0) + 1
    walk(suite)
    return found


def run_class(name, patterns):
    start = time.monotonic()
    done = subprocess.run([sys.executable, '-m', 'unittest', '-v',
                           *(f'-k{p}' for p in patterns), name],
                          cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return name, done.returncode, done.stdout, time.monotonic() - start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-j', '--jobs', type=int, default=1)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('-k', dest='patterns', action='append', default=[])
    parser.add_argument('modules', nargs='*')
    args = parser.parse_args()
    if args.jobs == 1 and args.repeat == 1:
        command = [*args.modules, *(f'-k{p}' for p in args.patterns)]
        command = ['-v', *command] if command else ['discover', '-v', '-p', 'test_*.py']
        sys.exit(subprocess.run([sys.executable, '-m', 'unittest', *command], cwd=HERE).returncode)

    found = classes(args.modules, args.patterns)
    times = json.loads(TIMES.read_text()) if TIMES.exists() else {}
    # The longest classes first, so none starts last; a class not timed yet
    # counts 2 s a test.
    order = sorted(found, key=lambda name: -times.get(name, 2 * found[name]))
    start = time.monotonic()
    failed, ran, failures = [], 0, Counter()
    with ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(run_class, name, args.patterns)
                for _ in range(args.repeat) for name in order]
        for job in as_completed(jobs):
            name, code, output, took = job.result()
            print(f'== {name} ({took:.1f} s)\n{output}', flush=True)
            if not args.patterns:
                times[name] = round(took, 1)
            ran += sum(int(n) for n in re.findall(r'^Ran (\d+) tests? in', output, re.M))
            if code:
                failed.append(name)
                # A test's id, or the class's for setUpClass, or the class
                # if it died without a report.
                failures.update(set(re.findall(r'^(?:FAIL|ERROR): \S+ \(([\w.]+)\)', output, re.M))
                                or {name})
    TIMES.write_text(json.dumps(times, indent=0, sort_keys=True))
    print(f'Ran {ran} tests in {len(found)} classes'
          f'{f" {args.repeat} times" if args.repeat > 1 else ""} in '
          f'{time.monotonic() - start:.1f} s, {args.jobs} at a time')
    if failed:
        print('FAILED: ' + ', '.join(dict.fromkeys(failed)))
    if args.repeat > 1 and failures:
        print(f'Not passing every run of {args.repeat}:')
        for test, count in sorted(failures.items()):
            print(f'  {test}: failed {count}')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
