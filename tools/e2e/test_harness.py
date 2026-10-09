"""The harness leaves no browser behind when its run is killed (#321): not one
that relaunched itself (chrome://restart) when the run gets SIGTERM, as from
`tools/detach.sh --stop`, and not its own child when the run gets SIGKILL."""

import shutil
import signal
import subprocess
import sys
import unittest
from pathlib import Path

from harness import BINARY, Relaunched, processes, wait_for

# A run that starts a browser, maybe relaunches it, and waits to be killed.
RUN = """
import sys, time
import harness
browser = harness.Browser()
if sys.argv[1] == 'relaunch':
    try:
        browser.new_tab('chrome://restart')
    except OSError:  # the browser may be gone before it activates the tab
        pass
print(browser.root, browser.proc.pid, flush=True)
time.sleep(600)
"""


class HarnessTest(unittest.TestCase):

    def assert_nothing_left(self, how, number):
        """Kills a run with signal `number`: no process of it may stay."""
        if not BINARY.is_file():
            self.skipTest(f'no browser binary at {BINARY!s}')
        # Its stderr would show the KeyboardInterrupt that SIGTERM raises.
        run = subprocess.Popen([sys.executable, '-c', RUN, how], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, cwd=Path(__file__).parent)
        line = run.stdout.readline()
        if not line:
            self.fail(f'the run exited with {run.wait()} before starting its browser')
        root, pid = line.split()
        profile = Path(root) / 'profile'
        try:
            if how == 'relaunch':
                wait_for(lambda: (p := Relaunched.find(profile)) and p.pid != int(pid),
                         timeout=60, what='the relaunched browser')
            run.send_signal(number)
            run.wait(timeout=60)
            wait_for(lambda: not processes(root), timeout=30, what='no process of the run left')
        finally:
            for proc in processes(root):
                proc.kill()
            run.kill()
            run.stdout.close()
            run.wait()
            shutil.rmtree(root, ignore_errors=True)

    def test_relaunched_browser_ends_with_a_stopped_run(self):
        self.assert_nothing_left('relaunch', signal.SIGTERM)

    def test_browser_ends_with_a_killed_run(self):
        self.assert_nothing_left('start', signal.SIGKILL)


if __name__ == '__main__':
    unittest.main()
