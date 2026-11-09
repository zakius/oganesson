"""The harness leaves no browser behind when its run is killed: not one
that relaunched itself (chrome://restart) when the run gets SIGTERM, as from
`tools/detach.sh --stop`, and not its own child when the run gets SIGKILL.
Its add-on helpers load an add-on from an .xpi and find its ID, background,
errors and popup."""

import json
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from harness import (BINARY, DEVELOPER_MODE, BrowserTest, Relaunched, extension_id, processes,
                     unpack_xpi, wait_for)

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


# A small add-on as AMO has most: Manifest V2 with Firefox's own key, a
# background page that logs a message and throws an error, and a popup.
ADD_ON = {
    'manifest.json': json.dumps({
        'manifest_version': 2,
        'name': 'Harness test add-on',
        'version': '1',
        'browser_specific_settings': {'gecko': {'id': 'harness@oganesson.test'}},
        'background': {'scripts': ['background.js']},
        'browser_action': {'default_popup': 'popup.html'},
    }),
    'background.js': ("self.started = true; console.error('harness: logged');"
                      " setTimeout(() => { throw new Error('harness: thrown'); });"),
    'popup.html': '<!doctype html><title>popup</title><p>popup</p>',
}


class ExtensionHelpersTest(BrowserTest):
    prefs = DEVELOPER_MODE

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-harness-add-on-'))
        xpi = cls.folder / 'add-on.xpi'
        with zipfile.ZipFile(xpi, 'w') as archive:
            for name, text in ADD_ON.items():
                archive.writestr(name, text)
        cls.unpacked = unpack_xpi(xpi, cls.folder / 'unpacked')
        cls.browser_args = (f'--load-extension={cls.unpacked}',)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.folder)

    def test_add_on_helpers(self):
        extension = extension_id(self.unpacked)
        background = self.browser.extension_background(extension)
        try:
            wait_for(lambda: background.eval('self.started === true'), what='the background script')
        finally:
            background.close()

        # The background's start shows in its console messages.
        def errors_with(text):
            found = self.browser.extension_errors(extension)
            return found if any(text in e for e in found) else None
        found = wait_for(lambda: errors_with('Uncaught Error: harness: thrown'),
                         what='the thrown error in the console messages')
        self.assertTrue(any('harness: logged' in e for e in found), found)
        # chrome://extensions keeps the errors from then on.
        background = self.browser.extension_background(extension)
        try:
            background.eval("setTimeout(() => { throw new Error('harness: later'); }); 1")
        finally:
            background.close()
        wait_for(lambda: 'Uncaught Error: harness: later' in self.browser.extension_errors(extension),
                 what="chrome://extensions' runtime error")

        popup = self.browser.open_popup(extension)
        try:
            wait_for(lambda: popup.eval('document.title') == 'popup', what='the popup')
        finally:
            popup.close()


if __name__ == '__main__':
    unittest.main()
