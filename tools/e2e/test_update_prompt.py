"""The update prompt after a package upgrade (patches/oganesson/core/update-prompt.patch). apt and
dnf put a new file at the binary's path, also for a rebuild on the same Chromium version; within
seconds the app menu button shows "Update", and its "Relaunch to update" restarts the browser on
the new file with its windows, tabs and back history, also with every switch that stops saving
history on (UpdatePromptNoHistoryTest).

The browser runs from a folder of links to the build's files, with its binary hard-linked, so the
test can replace the binary as a package upgrade does without touching the build.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import harness
from harness import BrowserTest, Server, wait_for

HTML = {'Content-Type': 'text/html'}


def page(title):
    return (200, HTML, f'<!doctype html><title>{title}</title>'.encode())


def install(folder):
    """The build's folder, linked into `folder`; returns the binary there."""
    built = harness.BINARY
    for entry in built.parent.iterdir():
        if entry.name != built.name:
            (folder / entry.name).symlink_to(entry)
    binary = folder / built.name
    try:
        os.link(built, binary)
    except OSError:  # another file system
        shutil.copy2(built, binary)
    return binary


def upgrade(binary):
    """A new file at the binary's path, as dpkg and rpm write one: a copy
    renamed over it."""
    new = binary.with_name(binary.name + '.dpkg-new')
    shutil.copy2(binary, new)
    os.replace(new, binary)


class UpdatePromptTest(BrowserTest):
    """Steps run in order and build on each other."""

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/a': page('a'), '/b': page('b'), '/c': page('c')})
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-install-'))
        built = harness.BINARY
        if built.is_file():
            harness.BINARY = install(cls.folder)
        try:
            super().setUpClass()
        finally:
            harness.BINARY = built

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def update_chips(self):
        return [v for v in self.browser.views('BrowserAppMenuButton')
                if v.visible and 'Update' in v.props.values()]

    def test_1_relaunch_after_upgrade(self):
        a, b, c = (self.server.url(p) for p in ('/a', '/b', '/c'))
        tab = self.browser.new_tab(a)
        wait_for(lambda: tab.eval('document.title') == 'a', what='page a')
        tab.eval(f'location.href = {b!r}')
        wait_for(lambda: self.browser.page('/b'), what='page b')
        self.browser.browser_call('Target.createTarget', url=c, newWindow=True)
        wait_for(lambda: self.browser.page('/c'), what='page c in a new window')
        self.assertEqual(self.update_chips(), [], 'an update chip before any upgrade')

        upgrade(self.browser.binary)
        # The poller looks ten seconds after the install folder changes.
        chip = wait_for(lambda: next(iter(self.update_chips()), None), timeout=60,
                        what='the Update chip')
        self.browser.click_view(chip)
        item = wait_for(lambda: next((v for menu in self.browser.menus() for group in menu
                                      for v in group
                                      if v['Title'].replace('&', '').startswith('Relaunch to update')),
                                     None), what='Relaunch to update in the app menu')
        self.browser.click_view(item)
        self.browser.follow_relaunch()

        # Both windows, the tab's back history, and no chip: the new process
        # runs the new file.
        restored = self.browser.page('/b', timeout=30)
        self.browser.page('/c', timeout=30)
        windows = {self.browser.browser_call('Browser.getWindowForTarget',
                                             targetId=t['id'])['windowId']
                   for t in self.browser.targets()
                   if t['type'] == 'page' and t['url'] in (b, c)}
        self.assertEqual(len(windows), 2, 'the two windows')
        restored.eval('history.back()')
        wait_for(lambda: restored.eval('location.href') == a, what='back to page a')
        self.assertEqual(self.update_chips(), [], 'an update chip after the relaunch')
        if self.prefs:
            # The switches were on in the profile the relaunched browser runs on.
            prefs = json.loads((self.browser.profile / 'Default/Preferences').read_text())
            self.assertTrue(prefs['history']['saving_disabled'])
            self.assertTrue(prefs['oganesson']['downloads']['saving_disabled'])
            self.assertFalse(prefs['oganesson']['history']['keep_closed_tabs'])


class UpdatePromptNoHistoryTest(UpdatePromptTest):
    """The same with browsing and download history not saved and closed tabs not kept: the
    session that relaunch restores isn't history."""
    prefs = {'history': {'saving_disabled': True},
             'oganesson': {'downloads': {'saving_disabled': True},
                           'history': {'keep_closed_tabs': False}}}
