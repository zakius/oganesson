"""Keyboard shortcuts with real key presses: most recently used tab cycling
after Ctrl+W closes a tab mid-cycle, and recording browser shortcuts
such as Ctrl+T on the shortcuts page, also while another settings tab
of the window that recorded closes, and Ctrl+Tab and Ctrl+Shift+Tab
removed there staying off, also after a restart.
"""

import time
import unittest

from harness import BrowserTest, wait_for


# The shortcuts page element, through settings' shadow roots.
PAGE = """(function find(root) {
    for (const node of root.querySelectorAll('*')) {
        if (node.localName === 'settings-browser-shortcuts-page') return node;
        const inner = node.shadowRoot && find(node.shadowRoot);
        if (inner) return inner;
    }
    return null;
})(document)"""
# The Add button of the command that has Ctrl+Tab (Next tab).
NEXT_TAB_ADD = f"""(() => {{
    let row = {PAGE}.shadowRoot.querySelector('[data-serialized-accelerator="Control+Tab"]');
    while (row && !row.querySelector('.actions')) row = row.parentElement;
    return row.querySelector('.actions cr-button');
}})()"""


def tab(name):
    return f'data:text/html,<title>{name}</title>{name}'


class ShortcutsTest(BrowserTest):
    prefs = {'helium': {'browser': {'mru_tab_cycling': True}}}

    def pages(self):
        return [t for t in self.browser.targets() if t['type'] == 'page']

    def active(self):
        # DevTools lists pages by last activity, so the active tab first.
        return self.pages()[0]['title']

    def only_tabs(self, *names):
        """Opens a tab per name, activated in order, and closes the others."""
        before = self.pages()
        for name in names:
            self.browser.new_tab(tab(name))
        for target in before:
            self.browser._get(f'/json/close/{target["id"]}')
        wait_for(lambda: sorted(t['title'] for t in self.pages()) == sorted(names),
                 what=f'just the tabs {names}')
        wait_for(lambda: self.active() == names[-1], what=f'{names[-1]} active')

    def test_1_mru_cycling_after_closing_a_tab(self):
        self.only_tabs('A', 'B', 'C')
        self.browser.key('shift')  # gives the window the input focus
        # Ctrl stays down: Tab, W, Tab, Tab.
        self.browser.xdotool('keydown', 'ctrl', 'key', 'Tab')
        try:
            wait_for(lambda: self.active() == 'B', what='B, the previous tab')
            self.browser.xdotool('key', 'w')
            wait_for(lambda: len(self.pages()) == 2, what='B to close')
            self.browser.xdotool('key', 'Tab')
            wait_for(lambda: self.active() == 'C', what='C after B closed')
            self.browser.xdotool('key', 'Tab')
            wait_for(lambda: self.active() == 'A', what='A next')
        finally:
            self.browser.xdotool('keyup', 'ctrl')
        self.browser.key('ctrl+Tab')
        wait_for(lambda: self.active() == 'C', what='C, the most recent tab, after Ctrl went up')

    def test_2_record_reserved_shortcuts(self):
        settings = self.browser.new_tab('chrome://settings/system/shortcuts')
        wait_for(lambda: settings.eval(f'!!{PAGE}?.commandsLoaded_'), what='the shortcuts')
        self.browser.key('shift')  # gives the window the input focus
        settings.eval(f'{NEXT_TAB_ADD}.click()')
        wait_for(lambda: settings.eval(
            f"{PAGE}.shadowRoot.activeElement?.id === 'captureTarget'"),
            what='the recording area to take the focus')
        pages = len(self.pages())
        for keys, recorded in (('ctrl+t', 'Control+KeyT'), ('ctrl+w', 'Control+KeyW'),
                               ('ctrl+Tab', 'Control+Tab')):
            self.browser.xdotool('key', keys)
            wait_for(lambda: settings.eval(f'{PAGE}.capturedAccelerator_') == recorded,
                     what=f'{recorded} recorded')
            if keys == 'ctrl+t':
                # Its owner is named.
                wait_for(lambda: settings.eval(
                    f"{PAGE}.captureMessage_.toLowerCase().includes('new tab')"),
                    what='the owner of Ctrl+T')
            self.assertEqual(len(self.pages()), pages)
            self.assertTrue(self.pages()[0]['url'].startswith('chrome://settings'))
        self.assertTrue(settings.eval("location.pathname === '/system/shortcuts'"))
        # Escape closes the dialog; then the shortcuts work again.
        self.browser.xdotool('key', 'Escape')
        wait_for(lambda: not settings.eval(f'{PAGE}.showCaptureDialog_'), what='the dialog to close')
        self.browser.key('ctrl+t')
        wait_for(lambda: len(self.pages()) == pages + 1, what='Ctrl+T to open a tab')
        self.browser.key('ctrl+w')
        wait_for(lambda: len(self.pages()) == pages, what='Ctrl+W to close it')

    def test_2b_other_settings_tab_closing_keeps_recording(self):
        other = self.browser.new_tab('chrome://settings/system/shortcuts')
        wait_for(lambda: other.eval(f'!!{PAGE}?.commandsLoaded_'), what='the other shortcuts')
        # As its recording area's focus does; the tab then goes to the
        # background, which doesn't stop it.
        other.eval("chrome.send('setShortcutHandlingSuspended', [true])")
        settings = self.browser.new_tab('chrome://settings/system/shortcuts')
        wait_for(lambda: settings.eval(f'!!{PAGE}?.commandsLoaded_'), what='the shortcuts')
        self.browser.key('shift')  # gives the window the input focus
        settings.eval(f'{NEXT_TAB_ADD}.click()')
        wait_for(lambda: settings.eval(
            f"{PAGE}.shadowRoot.activeElement?.id === 'captureTarget'"),
            what='the recording area to take the focus')
        pages = len(self.pages()) - 1
        self.browser.close_target(other)
        wait_for(lambda: len(self.pages()) == pages, what='the other settings tab to close')
        self.browser.key('ctrl+t')
        wait_for(lambda: settings.eval(f'{PAGE}.capturedAccelerator_') == 'Control+KeyT',
                 what='Ctrl+T recorded')
        self.assertEqual(len(self.pages()), pages)
        self.browser.xdotool('key', 'Escape')
        wait_for(lambda: not settings.eval(f'{PAGE}.showCaptureDialog_'), what='the dialog to close')
        self.browser.key('ctrl+t')
        wait_for(lambda: len(self.pages()) == pages + 1, what='Ctrl+T to open a tab')

    def no_switch(self, keys, active):
        self.browser.key(keys)
        time.sleep(1)
        self.assertEqual(self.active(), active, f'{keys} switched tabs')

    def test_3_removed_ctrl_tab_stays_off(self):
        settings = self.browser.new_tab('chrome://settings/system/shortcuts')
        wait_for(lambda: settings.eval(f'!!{PAGE}?.commandsLoaded_'), what='the shortcuts')
        for accelerator in ('Control+Tab', 'Control+Shift+Tab'):
            remove = (f"{PAGE}.shadowRoot.querySelector("
                      f"'[data-serialized-accelerator=\"{accelerator}\"]')")
            settings.eval(f'{remove}.click()')
            wait_for(lambda: not settings.eval(f'!!{remove}'), what=f'{accelerator} removed')
        for restart in (False, True):
            if restart:
                self.browser.quit()
                self.browser.start()
            self.only_tabs('D', 'E')
            self.no_switch('ctrl+Tab', 'E')
            self.no_switch('ctrl+shift+Tab', 'E')
            # Next tab keeps its other shortcut.
            self.browser.key('ctrl+Next')
            wait_for(lambda: self.active() == 'D', what='Ctrl+PgDown to switch tabs')




if __name__ == '__main__':
    unittest.main()
