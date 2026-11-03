"""Installed web apps in the tray (docs/web-apps.md#tray). With the app settings
page's switch on, closing the app's window hides it, its page still running,
also with every other window closed, and launching the app shows that window
again as it was. Turning the switch off shows it; without the switch, the
window closes. System settings has no background apps switch.
"""

import json
import subprocess
import unittest

from harness import wait_for
from test_web_app_links import WebAppTest

TRAY_ITEM = ('document.querySelector("web-app-settings-app")?.shadowRoot?'
             '.querySelector("app-management-tray-item")')
HANDLER = ('(await import("chrome://resources/cr_components/app_management/'
           'app_management.mojom-webui.js")).browserProxyFactory.getInstance().handler')


class TrayTest(WebAppTest):

    def tearDown(self):
        self.set_tray(False)
        super().tearDown()

    def set_tray(self, on):
        """Turns the app's tray switch on or off on its settings page."""
        tab = self.browser.new_tab(f'chrome://app-settings/{self.app_id}')
        try:
            app_id = json.dumps(self.app_id)
            # The item loads its state with its own request; on the same pipe,
            # this one is answered after it.
            wait_for(lambda: tab.eval(
                f'(async () => {{ const item = {TRAY_ITEM};'
                f' if (item?.app?.id !== {app_id}) return false;'
                f' await {HANDLER}.getTrayApp({app_id});'
                ' await item.updateComplete; return true; })()'), what='the tray switch')
            tab.eval(f'(() => {{ const item = {TRAY_ITEM};'
                     f' if (item.enabled_ !== {json.dumps(on)}) item.click(); }})()')
            wait_for(lambda: tab.eval(f'(async () => (await {HANDLER}.getTrayApp({app_id}))'
                                      f'.enabled === {json.dumps(on)})()'),
                     what=f'the tray switch {"on" if on else "off"}')
        finally:
            self.browser.close_target(tab)

    def close_app_window(self):
        """Ctrl+Shift+W in the app window, found by its WM_CLASS instance name."""
        window = wait_for(lambda: next(iter(subprocess.run(
            ['xdotool', 'search', '--onlyvisible', '--classname', f'crx_{self.app_id}'],
            env=self.browser.env(), capture_output=True, text=True, check=False).stdout.split()),
            None), what='the app window')
        self.browser.xdotool('windowfocus', '--sync', window)
        self.browser.xdotool('key', 'ctrl+shift+w')

    @staticmethod
    def visibility(app):
        return app.eval('document.visibilityState', gesture=False)

    def test_close_hides_and_launch_shows(self):
        self.set_tray(True)
        app = self.launch_app(close=False)
        self.addCleanup(lambda: self.browser.close_target(app))
        app.eval('window.marker = 42', gesture=False)
        self.close_app_window()
        wait_for(lambda: self.visibility(app) == 'hidden', what='the window hidden')
        self.assertIn(app.id, [t['id'] for t in self.browser.targets()])
        # Every other window closed: the app keeps the browser running.
        for target in self.browser.targets():
            if target['type'] == 'page' and target['id'] != app.id:
                self.browser.close_window(target['id'])
        self.assertTrue(self.browser.alive())
        self.assertEqual(app.eval('window.marker', gesture=False), 42)
        # A launch shows the window, as it was, and opens no other.
        before = {t['id'] for t in self.browser.targets()}
        self.browser.pipe_call('PWA.launch', manifestId=self.manifest_id)
        wait_for(lambda: self.visibility(app) == 'visible', what='the window shown')
        self.assertEqual(app.eval('window.marker', gesture=False), 42)
        self.assertEqual({t['id'] for t in self.browser.targets()} - before, set())
        # A normal window again: closing the app's last would quit the browser,
        # which the other tests share.
        self.browser.new_tab('about:blank')

    def test_switch_off_shows_the_window(self):
        self.set_tray(True)
        app = self.launch_app(close=False)
        self.addCleanup(lambda: self.browser.close_target(app))
        self.close_app_window()
        wait_for(lambda: self.visibility(app) == 'hidden', what='the window hidden')
        self.set_tray(False)
        wait_for(lambda: self.visibility(app) == 'visible', what='the window shown')

    def test_without_the_switch_the_window_closes(self):
        app = self.launch_app(close=False)
        self.close_app_window()
        wait_for(lambda: app.id not in [t['id'] for t in self.browser.targets()],
                 what='the app window to close')

    def test_no_background_apps_setting(self):
        tab = self.browser.new_tab('chrome://settings/system')
        self.addCleanup(lambda: self.browser.close_target(tab))
        # Through the shadow roots: the page has rendered once hardware
        # acceleration's switch is there.
        find = ('(function find(root, selector) { const hit = root.querySelector(selector);'
                ' if (hit) return hit; for (const el of root.querySelectorAll("*"))'
                ' { const found = el.shadowRoot && find(el.shadowRoot, selector);'
                ' if (found) return found; } return null; })')
        wait_for(lambda: tab.eval(f'!!{find}(document, "#hardwareAcceleration")'),
                 what='the system settings page')
        self.assertFalse(tab.eval(f'!!{find}(document, \'[pref-key="background_mode.enabled"]\')'))


if __name__ == '__main__':
    unittest.main()
