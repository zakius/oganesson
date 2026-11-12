"""Containers (docs/containers.md): each container keeps its own cookies and
site storage. Tabs get into one from the menus, keep it for the links they
open and across a restart, with their sessionStorage, and Traffic Control
rules move pages into one.
The address bar shows the tab's container. A link dropped on the tab strip
and Alt+Enter in the address bar stay in the tab's container, the New Tab
button can ask where to open, and commands open a new tab in a container.
A site's zoom level is the same in every container. A click on a container's
notification reaches the container's service worker, and push subscriptions
fail in containers. A container's sessionStorage that no restored tab uses
goes at the next start.

The tests are steps of one session, in order. A tab's container shows in its
cookies: each tab sets a cookie named after where it is.
"""

import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from harness import BrowserTest, Page, Server, wait_for

PAGE = b'''<!doctype html><title>page</title>
<a id="blank" href="/other?blank" target="_blank">blank</a>
<a id="link" href="/other?link">link</a>
<p id="space" style="height: 200px">text</p>'''
OTHER = b'<!doctype html><title>other</title><p>other</p>'
# A service worker that tells its pages about a click on its notification.
WORKER = b'''self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({includeUncontrolled: true}).then(
      pages => pages.forEach(page => page.postMessage(event.notification.title))));
});'''
# The public key of the Web Push protocol's examples (RFC 8292).
PUSH_KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'
# The first element matching a selector, through every shadow root.
DEEP = """(selector => {
  const find = root => {
    const found = root.querySelector(selector);
    if (found) return found;
    for (const element of root.querySelectorAll('*')) {
      const inner = element.shadowRoot && find(element.shadowRoot);
      if (inner) return inner;
    }
    return null;
  };
  return find(document);
})"""


def storage_folder(profile, container_id):
    """Where Chromium keeps a container's storage (StoragePartitionImplMap)."""
    digest = hashlib.sha256(container_id.encode()).hexdigest()[:12].upper()
    return profile / 'Default/Storage/ext/containers' / digest


class ContainersTest(BrowserTest):
    # Continue where you left off, so that a restart restores the tabs.
    prefs = {'session': {'restore_on_startup': 1}}

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/page': (200, {'Content-Type': 'text/html'}, PAGE),
                             '/other': (200, {'Content-Type': 'text/html'}, OTHER),
                             '/popup': (200, {'Content-Type': 'text/html'}, OTHER),
                             '/worker.js': (200, {'Content-Type': 'text/javascript'}, WORKER)})
        # The test server may show notifications (step 9f).
        site = f'{cls.server.url("")},*'
        cls.prefs = {**cls.prefs, 'profile': {'content_settings': {'exceptions': {
            'notifications': {site: {'setting': 1}}}}}}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    # Helpers.

    def url(self, path, host='127.0.0.1'):
        return self.server.url(path, host)

    def pages(self):
        return {t['id']: t['url'] for t in self.browser.targets() if t['type'] == 'page'}

    def new_page(self, before, url_part=''):
        """The page target that isn't in `before`, once its URL has `url_part`."""
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['type'] == 'page' and t['id'] not in before
                                        and url_part in t['url']), None),
                          what=f'a new tab with {url_part!r}')
        return Page(target)

    def menu_item(self, title):
        return wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                      for i in group if i['Title'] == title), None),
                        what=f'the menu item "{title}"')

    def choose(self, *titles):
        """Clicks each of `titles` in the open menus: a submenu, then its item."""
        for title in titles:
            self.browser.click_view(self.menu_item(title))
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def new_tab_in(self, container):
        """Opens a new tab in `container` from the New Tab button's menu and
        loads the test page in it."""
        before = self.pages()
        self.browser.click_view(self.new_tab_button(), button=3)
        self.choose('New tab in container', container)
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['type'] == 'page' and t['id'] not in before),
                                       None), what='the new tab')
        page = Page(target)
        page.call('Page.navigate', url=self.url('/page'))
        wait_for(lambda: page.eval('document.title') == 'page', what='the page')
        return page

    def new_tab_button(self):
        """The New Tab button, once no tab is closing. A closed tab's view
        shrinks away after its tab has gone, and the button moves with it: a
        slow frame can hold it still long enough to look settled."""
        def button():
            tabs = [v for v in self.browser.views('Tab') if v.visible]
            pages = [t for t in self.browser.targets() if t['type'] == 'page']
            if len(tabs) != len(pages):
                return None
            return next((v for v in self.browser.views('TabStripControlButton')
                         if v.visible and v.props.get('TooltipText', '').startswith('New tab')),
                        None)
        return self.browser.wait_settled(button, what='the New Tab button, no tab closing')

    def page_tabs(self):
        """The test pages' tabs, attached."""
        return [Page(t) for t in self.browser.targets()
                if t['type'] == 'page' and f':{self.server.port}/' in t['url']]

    def cookie_now(self, page):
        """The page's cookies, or None while it isn't a loaded http page, as
        a restored tab that hasn't loaded."""
        return page.eval("location.protocol === 'http:' && document.readyState === 'complete'"
                         " ? document.cookie : null")

    def cookie(self, page, timeout=15):
        """The page's cookies, once it has loaded."""
        return wait_for(lambda: (lambda c: c is not None and [c])(self.cookie_now(page)),
                        timeout=timeout, what='the page to load')[0]

    def set_cookie(self, page, name):
        page.eval(f"document.cookie = 'in={name}; max-age=86400'")

    def settings(self):
        page = self.browser.new_tab('chrome://settings/containers')
        wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
        return page

    def set_pref(self, name, value):
        page = self.settings()
        try:
            page.eval(f'chrome.settingsPrivate.setPref({json.dumps(name)}, {json.dumps(value)})')
        finally:
            self.browser.close_target(page)

    def get_pref(self, name):
        page = self.settings()
        try:
            return page.eval(f'chrome.settingsPrivate.getPref({json.dumps(name)})'
                             '.then(p => p.value)')
        finally:
            self.browser.close_target(page)

    # Steps.

    def test_1_isolation(self):
        default = self.browser.new_tab(self.url('/page'))
        wait_for(lambda: default.eval('document.title') == 'page', what='the page')
        self.set_cookie(default, 'default')
        work = self.new_tab_in('Work')
        self.assertEqual(self.cookie(work), '')
        self.set_cookie(work, 'work')
        personal = self.new_tab_in('Personal')
        self.assertEqual(self.cookie(personal), '')
        self.set_cookie(personal, 'personal')
        default.call('Page.reload')
        wait_for(lambda: default.eval('document.readyState') == 'complete', what='the reload')
        self.assertEqual(self.cookie(default), 'in=default')
        self.assertEqual(self.cookie(work), 'in=work')
        self.assertEqual(self.cookie(personal), 'in=personal')

    def work_page(self):
        """The Work tab of step 1, active."""
        page = next(p for p in self.page_tabs() if self.cookie_now(p) == 'in=work')
        page.call('Page.bringToFront')
        return page

    def tab_titled(self, title):
        """The view of the title of a tab, by its text."""
        return self.browser.wait_view('TabTitle', match=lambda v: title in v.props.values())

    def test_2_links_stay_in_the_container(self):
        work = self.work_page()
        for how, click in (('target=_blank', lambda: self.browser.click_element(work, '#blank')),
                           ('middle click', lambda: self.browser.click_element(work, '#link',
                                                                              button=2)),
                           ('window.open noopener', lambda: work.eval(
                               f"window.open({json.dumps(self.url('/other?noopener'))},"
                               " '_blank', 'noopener')")),
                           ('window.open', lambda: work.eval(
                               f"window.open({json.dumps(self.url('/other?opener'))}) && 1"))):
            with self.subTest(how):
                before = self.pages()
                click()
                page = self.new_page(before, '/other')
                wait_for(lambda: page.eval('document.title') == 'other', what='the link')
                self.assertEqual(self.cookie(page), 'in=work')
                self.browser.close_target(page)
                work.call('Page.bringToFront')

        # The link context menu opens a link in a container of choice.
        before = self.pages()
        self.browser.click_element(work, '#link', button=3)
        self.choose('Open link in container', 'Personal')
        page = self.new_page(before, '/other?link')
        wait_for(lambda: page.eval('document.title') == 'other', what='the link')
        self.assertEqual(self.cookie(page), 'in=personal')
        self.browser.close_target(page)

    def test_3_restore_after_restart(self):
        self.work_page().eval("document.title = 'pin me'")
        self.browser.click_view(self.tab_titled('pin me'), button=3)
        self.choose('Pin')
        # Each tab's sessionStorage says where it is, as its cookie does.
        for page in self.page_tabs():
            page.eval("sessionStorage.setItem('in', document.cookie.slice(3))")
        tabs = len(self.page_tabs())
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: len(self.page_tabs()) == tabs, what='every tab to be restored')
        # Restored tabs load when shown: each is shown in turn.
        cookies = []
        for page in self.page_tabs():
            page.call('Page.bringToFront')
            cookie = self.cookie(page, timeout=60)
            cookies.append(cookie)
            stored = page.eval("sessionStorage.getItem('in')")
            self.assertEqual(f'in={stored}', cookie)
        self.assertEqual(sorted(set(cookies)), ['in=default', 'in=personal', 'in=work'])

    def test_4_reopen_closed_tab(self):
        work = self.work_page()
        before = self.pages()
        work.eval(f"window.open({json.dumps(self.url('/other?closed'))}) && 1")
        page = self.new_page(before, '/other?closed')
        wait_for(lambda: page.eval('document.title') == 'other', what='the page')
        page.eval("sessionStorage.setItem('closed', 'kept')")
        self.browser.close_target(page)
        before = self.pages()
        self.browser.key('ctrl+shift+t')
        page = self.new_page(before, '/other?closed')
        wait_for(lambda: page.eval('document.title') == 'other', what='the reopened tab')
        self.assertEqual(self.cookie(page), 'in=work')
        self.assertEqual(page.eval("sessionStorage.getItem('closed')"), 'kept')
        self.browser.close_target(page)

    def test_4a_browser_page_keeps_the_container(self):
        # A Work tab that shows a browser page restores in Work, after a
        # restart and reopened: Back loads its site with Work's cookie.
        work = self.new_tab_in('Work')
        work.call('Page.navigate', url='chrome://version')
        wait_for(lambda: work.eval('location.href') == 'chrome://version/',
                 what='the browser page')

        def back_in_work():
            page = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                               if t['url'] == 'chrome://version/'), None),
                                 timeout=30, what='the restored browser page'))
            page.call('Page.bringToFront')
            wait_for(lambda: page.eval('document.readyState') == 'complete',
                     timeout=60, what='the browser page to load')
            page.eval('history.back()')
            wait_for(lambda: page.eval('location.pathname') == '/page', what='Back')
            self.assertEqual(self.cookie(page), 'in=work')
            page.call('Page.navigate', url='chrome://version')
            wait_for(lambda: page.eval('location.href') == 'chrome://version/',
                     what='the browser page')
            return page

        tabs = len(self.page_tabs())
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: len(self.page_tabs()) == tabs, what='every tab to be restored')
        # The other restored tabs load when shown, so the next steps can read them.
        for other in self.page_tabs():
            other.call('Page.bringToFront')
            self.cookie(other, timeout=60)
        page = back_in_work()
        self.browser.close_target(page)
        wait_for(lambda: not [t for t in self.browser.targets()
                              if t['url'] == 'chrome://version/'], what='the tab to close')
        self.browser.key('ctrl+shift+t')
        self.browser.close_target(back_in_work())

    def test_5_traffic_control(self):
        # localhost's cookie in Work tells the rule's tab apart.
        before = self.pages()
        work = self.work_page()
        work.call('Page.navigate', url=self.url('/page', 'localhost'))
        wait_for(lambda: work.eval('document.title') == 'page', what='the page')
        self.set_cookie(work, 'work')
        self.set_pref('containers.traffic_control',
                      [{'url_filter': 'localhost', 'container': 'work', 'enabled': True}])
        default = self.browser.new_tab(self.url('/page'))
        wait_for(lambda: default.eval('document.title') == 'page', what='the page')
        before = self.pages()
        default.eval(f"location.href = {json.dumps(self.url('/other?rule', 'localhost'))}")
        page = self.new_page(before, '/other?rule')
        wait_for(lambda: page.eval('document.title') == 'other', what='the rule\'s tab')
        self.assertEqual(self.cookie(page), 'in=work')
        # The tab it left keeps its page.
        self.assertEqual(default.eval('location.pathname'), '/page')
        self.browser.close_target(page)
        # A popup that its page holds as window.opener (an OAuth popup): its
        # page opens in the rule's container, and the popup stays open.
        before = self.pages()
        default.eval(f"self.popup = window.open({json.dumps(self.url('/popup', 'localhost'))}); 1")
        page = wait_for(lambda: self.loaded_in(before, '/popup', 'in=work'),
                        what="the rule's tab")
        self.assertFalse(default.eval('popup.closed'))
        default.eval('popup.close()')
        self.browser.close_target(page)
        wait_for(lambda: self.pages().keys() == before.keys(), what='the popup to close')
        # A form post stays in its tab, with its data: a reopened page has none.
        before = self.pages()
        default.eval("const form = document.createElement('form'); form.method = 'post';"
                     f" form.action = {json.dumps(self.url('/other?post', 'localhost'))};"
                     " form.innerHTML = '<input name=q value=sent>';"
                     " document.body.append(form); form.submit(); 1")
        wait_for(lambda: default.eval("location.search + ' ' + document.title") == '?post other',
                 what='the form post')
        self.assertEqual(self.server.bodies.get('/other'), b'q=sent')
        self.assertEqual(self.cookie(default), '')
        self.assertEqual(self.pages().keys(), before.keys())
        self.browser.close_target(default)
        self.set_pref('containers.traffic_control', [])

    def loaded_in(self, before, url_part, cookie):
        """A new tab, not in `before`, that has loaded `url_part` with
        `cookie`, or None."""
        for target in self.browser.targets():
            if (target['type'] != 'page' or target['id'] in before
                    or url_part not in target['url']):
                continue
            page = Page(target)
            if self.cookie_now(page) == cookie:
                return page
            page.close()
        return None

    def test_6_temporary_containers(self):
        first = self.new_tab_in('New temporary container')
        self.assertEqual(self.cookie(first), '')
        self.set_cookie(first, 'temporary')
        second = self.new_tab_in('New temporary container')
        self.assertEqual(self.cookie(second), '')
        self.browser.close_target(second)

    def test_7_new_tabs_open_in_a_container(self):
        self.set_pref('containers.new_tab', 'work')
        try:
            before = self.pages()
            self.browser.key('ctrl+t')
            target = wait_for(lambda: next((t for t in self.browser.targets()
                                            if t['type'] == 'page' and t['id'] not in before),
                                           None), what='the new tab')
            page = Page(target)
            page.call('Page.navigate', url=self.url('/page'))
            self.assertEqual(self.cookie(page), 'in=work')
            self.browser.close_target(page)
        finally:
            self.set_pref('containers.new_tab', '')

    def test_8_delete_container(self):
        personal = next(c for c in self.get_pref('containers.list') if c['name'] == 'Personal')
        folder = storage_folder(self.browser.profile, personal['id'])
        wait_for(folder.exists, what="Personal's storage")
        page = self.settings()
        try:
            rows = f"{DEEP}('settings-containers-page').shadowRoot"
            wait_for(lambda: page.eval(f'!!{DEEP}("settings-containers-page")'
                                       '?.shadowRoot?.querySelector(".container")'),
                     what='the containers')
            page.eval(f"[...{rows}.querySelectorAll('.container')].find(r => "
                      "r.textContent.includes('Personal')).querySelector('.delete').click()")
            wait_for(lambda: page.eval(f'!!{rows}.querySelector("#confirmDelete")'),
                     what='the delete dialog')
            page.eval(f'{rows}.querySelector("#confirmDelete").click()')
        finally:
            self.browser.close_target(page)
        # Its tabs close, and its storage goes.
        wait_for(lambda: not [p for p in self.page_tabs()
                              if self.cookie_now(p) == 'in=personal'],
                 what="Personal's tab to close")
        self.assertNotIn('Personal', [c['name'] for c in self.get_pref('containers.list')])
        # The last session had a tab in it: its storage goes at the next start.
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: not folder.exists(), what="Personal's storage to go")
        # Another container doesn't get its cookies.
        self.browser.click_view(self.new_tab_button(), button=3)
        self.browser.click_view(self.menu_item('New tab in container'))
        self.menu_item('Work')
        titles = [i['Title'] for menu in self.browser.menus() for group in menu for i in group]
        self.browser.key('Escape')
        self.browser.key('Escape')
        self.assertNotIn('Personal', titles)
        self.assertIn('Work', titles)

    def test_8a_deleted_container_is_not_restored(self):
        # A tab of a container deleted while the browser was closed, as when
        # a tab stayed open after the deletion, restores in a new temporary
        # container, not with the deleted container's cookies.
        listed = self.get_pref('containers.list')
        gone = {'id': 'gone', 'name': 'Gone', 'icon': 'circle', 'color': 'red'}
        self.set_pref('containers.list', listed + [gone])
        page = self.new_tab_in('Gone')
        page.call('Page.navigate', url=self.url('/page?gone'))
        wait_for(lambda: page.eval('location.search') == '?gone', what='the page')
        self.set_cookie(page, 'gone')
        self.assertEqual(self.cookie(page), 'in=gone')
        self.browser.quit()
        preferences = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(preferences.read_text())
        prefs['containers']['list'] = [c for c in prefs['containers']['list']
                                       if c['id'] != 'gone']
        preferences.write_text(json.dumps(prefs))
        self.browser.start()
        page = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['type'] == 'page' and t['url'].endswith('?gone')),
                                          None), what='the restored tab'))
        page.call('Page.bringToFront')
        self.assertEqual(self.cookie(page, timeout=60), '')
        self.assertNotIn('gone', [c['id'] for c in self.get_pref('containers.list')])
        self.browser.close_target(page)

    def container_icons(self):
        return [v for v in self.browser.views('PageActionView')
                if v.visible and v['TooltipText'].startswith('Container: ')]

    def test_9_address_bar_icon(self):
        work = self.new_tab_in('Work')
        icon = self.browser.wait_view(
            'PageActionView', match=lambda v: v['TooltipText'] == 'Container: Work')
        # A click opens the menu to reopen the tab in another container.
        self.browser.click_view(icon)
        self.menu_item('No container')
        titles = [i['Title'] for menu in self.browser.menus() for group in menu for i in group]
        self.browser.key('Escape')
        self.assertNotIn('Work', titles)
        self.assertIn('Manage containers…', titles)
        # A tab outside containers has none.
        other = self.browser.new_tab(self.url('/other'))
        wait_for(lambda: other.eval('document.title') == 'other', what='the page')
        wait_for(lambda: not self.container_icons(), what='no container icon')
        self.browser.close_target(other)
        self.browser.close_target(work)

    # Step 8's restart left the restored tabs unloaded: the steps below open
    # a Work tab of their own.

    def test_9a_dropped_link_stays_in_the_container(self):
        work = self.new_tab_in('Work')
        contents = self.browser.wait_view('ContentsWebView').bounds
        x, y = work.eval('(() => { const r = document.getElementById("link")'
                         '.getBoundingClientRect(); return [r.x + 5, r.y + r.height / 2]; })()')
        start = (contents['x'] + int(x), contents['y'] + int(y))
        # Past the end of the tabs, so the link opens in a new tab there.
        button = self.new_tab_button().bounds
        end = (button['x'] + button['width'] + 60, button['y'] + button['height'] // 2)
        before = self.pages()
        self.browser.xdotool('mousemove', str(start[0]), str(start[1]), 'mousedown', '1')
        for step in range(1, 21):
            self.browser.xdotool('mousemove', str(start[0] + (end[0] - start[0]) * step // 20),
                                 str(start[1] + (end[1] - start[1]) * step // 20))
            time.sleep(0.05)
        time.sleep(0.5)
        self.browser.xdotool('mouseup', '1')
        page = wait_for(lambda: self.loaded_in(before, '/other?link', 'in=work'),
                        what='the dropped link in Work')
        self.browser.close_target(page)
        self.browser.close_target(work)

    def test_9b_alt_enter_stays_in_the_container(self):
        work = self.new_tab_in('Work')
        before = self.pages()
        self.browser.key('ctrl+l')
        self.browser.xdotool('type', '--delay', '20', self.url('/other?alt'))
        self.browser.key('alt+Return')
        page = wait_for(lambda: self.loaded_in(before, '/other?alt', 'in=work'),
                        what='the address in Work')
        self.browser.close_target(page)
        self.browser.close_target(work)

    def test_9c_ask_for_new_tabs(self):
        self.set_pref('containers.new_tab', 'ask')
        try:
            before = self.pages()
            self.browser.click_view(self.new_tab_button())
            self.menu_item('No container')
            self.choose('Work')
            target = wait_for(lambda: next((t for t in self.browser.targets()
                                            if t['type'] == 'page' and t['id'] not in before),
                                           None), what='the new tab')
            page = Page(target)
            page.call('Page.navigate', url=self.url('/page'))
            self.assertEqual(self.cookie(page), 'in=work')
            self.browser.close_target(page)
            # Ctrl+T opens a tab outside containers.
            before = self.pages()
            self.browser.key('ctrl+t')
            target = wait_for(lambda: next((t for t in self.browser.targets()
                                            if t['type'] == 'page' and t['id'] not in before),
                                           None), what='the new tab')
            page = Page(target)
            page.call('Page.navigate', url=self.url('/page'))
            self.assertEqual(self.cookie(page), 'in=default')
            self.browser.close_target(page)
        finally:
            self.set_pref('containers.new_tab', '')

    def test_9d_new_tab_commands(self):
        # Ctrl+Shift+1 is the first container's: Work, since step 8 deleted
        # Personal.
        self.assertEqual(self.get_pref('containers.list')[0]['name'], 'Work')
        before = self.pages()
        self.browser.key('ctrl+shift+1')
        target = wait_for(lambda: next((t for t in self.browser.targets()
                                        if t['type'] == 'page' and t['id'] not in before),
                                       None), what='the new tab')
        page = Page(target)
        page.call('Page.navigate', url=self.url('/page'))
        self.assertEqual(self.cookie(page), 'in=work')
        self.browser.close_target(page)
        # The shortcuts page lists the commands.
        settings = self.browser.new_tab('chrome://settings/system/shortcuts')
        try:
            page_text = (f"{DEEP}('settings-browser-shortcuts-page')"
                         "?.shadowRoot?.textContent || ''")
            wait_for(lambda: 'New tab in container 9' in settings.eval(page_text),
                     what='the commands on the shortcuts page')
            self.assertIn("New tab in the current tab's container", settings.eval(page_text))
        finally:
            self.browser.close_target(settings)

    def test_9e_zoom_is_shared(self):
        # A site's zoom level is the same in every container, as in Firefox.
        url = self.url('/other?zoom', 'localhost')
        default = self.browser.new_tab(url)
        wait_for(lambda: default.eval('document.title') == 'other', what='the page')
        ratio = default.eval('devicePixelRatio')
        default.call('Page.bringToFront')
        self.browser.key('ctrl+equal')
        wait_for(lambda: default.eval('devicePixelRatio') > ratio, what='the zoom')
        zoomed = default.eval('devicePixelRatio')
        try:
            work = self.new_tab_in('Work')
            work.call('Page.navigate', url=url)
            wait_for(lambda: work.eval('document.title') == 'other', what='the page in Work')
            wait_for(lambda: work.eval('devicePixelRatio') == zoomed, what="the site's zoom in Work")
            self.browser.close_target(work)
        finally:
            default.call('Page.bringToFront')
            self.browser.key('ctrl+0')
            self.browser.close_target(default)


    def register_worker(self, page):
        """Registers WORKER for `page`, whose clicked notifications' titles
        go into window.clicked."""
        page.eval("window.clicked = []; navigator.serviceWorker.onmessage ="
                  " event => window.clicked.push(event.data);"
                  " navigator.serviceWorker.register('/worker.js')"
                  ".then(() => navigator.serviceWorker.ready).then(() => true)")

    def test_9f_notifications_and_push(self):
        # Chromium sends a notification's click to the site's own partition:
        # a container's notification has to reach the container's worker.
        default = self.browser.new_tab(self.url('/other?notify'))
        wait_for(lambda: default.eval('document.title') == 'other', what='the page')
        work = self.new_tab_in('Work')
        try:
            self.register_worker(default)
            self.register_worker(work)
            work.eval("navigator.serviceWorker.ready.then(worker =>"
                      " worker.showNotification('from Work', {requireInteraction: true}))"
                      ".then(() => true)")
            popup = self.browser.wait_view('MessagePopupView')
            self.browser.click_view(popup)
            wait_for(lambda: work.eval('window.clicked.length'), what='the click in Work')
            self.assertEqual(work.eval('window.clicked'), ['from Work'])
            self.assertEqual(default.eval('window.clicked'), [])

            # Push goes to the site's own partition too, so containers have none.
            error = work.eval(
                "navigator.serviceWorker.ready.then(worker => worker.pushManager.subscribe("
                f"{{userVisibleOnly: true, applicationServerKey: '{PUSH_KEY}'}}))"
                ".then(() => 'subscribed', error => error.message)")
            self.assertIn('push service not available', error)
        finally:
            self.browser.close_target(work)
            self.browser.close_target(default)


class ContainersStaleSessionStorageTest(BrowserTest):
    """A Work tab's sessionStorage stays while a restored tab uses it, and goes
    from the disk at a start without the last session, as the default
    partition's does. The SQLite backend holds it here, so the test can read
    it; both backends share the code that deletes it."""
    browser_args = ('--enable-features=DomStorageSqlite',)
    # Continue where you left off, and new tabs open in Work.
    prefs = {'session': {'restore_on_startup': 1}, 'containers': {'new_tab': 'work'}}
    NOTE = 'left behind'

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/page': (200, {'Content-Type': 'text/html'}, PAGE)})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def note_on_disk(self):
        """Whether Work's sessionStorage on disk holds the note, or None while
        it can't be read. Reads a copy: the browser holds the database, and
        SQLite may delete its files while the browser runs."""
        database = storage_folder(self.browser.profile, 'work') / 'SessionStorage'
        if not database.exists():
            return False
        with tempfile.TemporaryDirectory() as copy:
            try:
                for suffix in ('', '-wal'):
                    if Path(f'{database}{suffix}').exists():
                        shutil.copy(f'{database}{suffix}', f'{copy}/db{suffix}')
            except FileNotFoundError:
                return None
            try:
                with closing(sqlite3.connect(f'{copy}/db')) as db:
                    values = [bytes(v) for (v,) in db.execute('SELECT value FROM map_entries')]
            except sqlite3.DatabaseError:
                return None
        return any(self.NOTE.encode(encoding) in value
                   for value in values for encoding in ('latin-1', 'utf-16-le'))

    def work_page(self):
        """The test page's tab, loaded and shown."""
        page = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['type'] == 'page'
                                           and f':{self.server.port}/' in t['url']), None),
                             timeout=30, what='the Work tab'))
        page.call('Page.bringToFront')
        wait_for(lambda: page.eval("document.readyState === 'complete'"), timeout=60,
                 what='the page to load')
        return page

    def test_unused_session_storage_goes(self):
        before = {t['id'] for t in self.browser.targets()}
        self.browser.key('ctrl+t')
        page = Page(wait_for(lambda: next((t for t in self.browser.targets()
                                           if t['type'] == 'page' and t['id'] not in before),
                                          None), what='the new tab'))
        page.call('Page.navigate', url=self.server.url('/page'))
        wait_for(lambda: page.eval('document.title') == 'page', what='the page')
        page.eval(f"sessionStorage.setItem('note', {json.dumps(self.NOTE)})")
        self.browser.quit()
        self.assertTrue(self.note_on_disk(), "the note in Work's sessionStorage")

        # The restored Work tab keeps it.
        self.browser.start()
        self.assertEqual(self.work_page().eval("sessionStorage.getItem('note')"), self.NOTE)
        self.browser.quit()
        self.assertTrue(self.note_on_disk(), 'the note after the restore')

        # A start without the last session deletes it.
        preferences = self.browser.profile / 'Default/Preferences'
        prefs = json.loads(preferences.read_text())
        prefs['session']['restore_on_startup'] = 5  # the New Tab page
        preferences.write_text(json.dumps(prefs))
        self.browser.start()
        wait_for(lambda: self.note_on_disk() is False, timeout=30,
                 what="the note to go from Work's sessionStorage")
        self.browser.quit()
        self.assertIs(self.note_on_disk(), False)
        self.browser.start()


class ContainersTabLineTest(BrowserTest):
    """Tabs in a container have a line in its color, which follows the
    container's color as it changes."""
    tab_class = 'Tab'

    def tab_views(self):
        """The tabs, in order."""
        return self.browser.wait_settled(
            lambda: sorted((v for v in self.browser.views(self.tab_class) if v.visible),
                           key=lambda v: (v.bounds['y'], v.bounds['x'])), what='the tabs')

    def line_colors(self, view):
        """The colors along the bottom of a tab, where the line is."""
        b = view.bounds
        bottom = b['y'] + b['height']
        return {self.browser.pixel(b['x'] + b['width'] // 2, y)
                for y in range(bottom - 10, bottom)}

    def work_color(self, settings):
        """Work's color, as Settings shows it."""
        icon = (f"{DEEP}('settings-containers-page')?.shadowRoot"
                "?.querySelector('.container-icon')")
        wait_for(lambda: settings.eval(f'!!{icon}'), what='the containers')
        # "rgb(r, g, b)"
        work = settings.eval(f"getComputedStyle([...{DEEP}('settings-containers-page')"
                             ".shadowRoot.querySelectorAll('.container')].find(r => "
                             "r.textContent.includes('Work')).querySelector('.container-icon'))"
                             ".backgroundColor")
        return tuple(int(n) for n in work[work.index('(') + 1:work.index(')')].split(',')[:3])

    def test_color_line(self):
        settings = self.browser.new_tab('chrome://settings/containers')
        wait_for(lambda: settings.eval('!!chrome.settingsPrivate'), what='Settings')
        settings.eval("chrome.settingsPrivate.setPref('containers.new_tab', 'work')")
        color = self.work_color(settings)
        before = len(self.tab_views())
        self.browser.key('ctrl+t')
        wait_for(lambda: len(self.tab_views()) == before + 1, what='the new tab')
        tabs = self.tab_views()
        wait_for(lambda: color in self.line_colors(self.tab_views()[-1]),
                 what="the Work tab's line")
        self.assertNotIn(color, self.line_colors(tabs[0]))

        # Work gets another color while its tab is in the background, which
        # nothing else repaints: the tab's line follows.
        settings.call('Page.bringToFront')
        wait_for(lambda: color in self.line_colors(self.tab_views()[-1]),
                 what="the background Work tab's line")
        containers = settings.eval("chrome.settingsPrivate.getPref('containers.list')"
                                   ".then(p => p.value)")
        work = next(c for c in containers if c['id'] == 'work')
        work['color'] = 'purple' if work['color'] != 'purple' else 'green'
        settings.eval("chrome.settingsPrivate.setPref('containers.list', "
                      f"{json.dumps(containers)})")
        new_color = wait_for(lambda: (lambda c: c != color and c)(self.work_color(settings)),
                             what="Work's new color in Settings")
        wait_for(lambda: new_color in self.line_colors(self.tab_views()[-1]),
                 what="the Work tab's new line")
        self.browser.close_target(settings)


class ContainersVerticalTabsTest(ContainersTabLineTest):
    """Vertical tabs mark container tabs with the same color line."""
    prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout
    tab_class = 'TabView'


class ContainersPolishTest(BrowserTest):
    """Settings names the colors and icons in the user's language."""
    browser_args = ('--lang=pl',)
    browser_env = {'LANGUAGE': 'pl'}

    def test_color_and_icon_names(self):
        page = self.browser.new_tab('chrome://settings/containers')
        root = f"{DEEP}('settings-containers-page')?.shadowRoot"
        wait_for(lambda: page.eval(f"!!{root}?.querySelector('#addContainer')"),
                 what='the containers page')
        page.eval(f"{root}.querySelector('#addContainer').click()")
        wait_for(lambda: page.eval(f"!!{root}.querySelector('#colors .choice')"),
                 what='the container dialog')

        def labels(list_id):
            return page.eval(f"[...{root}.querySelectorAll('#{list_id} .choice')]"
                             ".map(b => b.getAttribute('aria-label'))")
        self.assertIn('Niebieski', labels('colors'))
        self.assertIn('Odcisk palca', labels('icons'))


if __name__ == '__main__':
    unittest.main()

