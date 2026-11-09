"""Containers (docs/containers.md): each container keeps its own cookies and
site storage. Tabs get into one from the menus, keep it for the links they
open and across a restart, and Traffic Control rules move pages into one.

The tests are steps of one session, in order. A tab's container shows in its
cookies: each tab sets a cookie named after where it is.
"""

import hashlib
import json
import unittest

from harness import BrowserTest, Page, Server, wait_for

PAGE = b'''<!doctype html><title>page</title>
<a id="blank" href="/other?blank" target="_blank">blank</a>
<a id="link" href="/other?link">link</a>
<p id="space" style="height: 200px">text</p>'''
OTHER = b'<!doctype html><title>other</title><p>other</p>'
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
                             '/other': (200, {'Content-Type': 'text/html'}, OTHER)})
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
        return self.browser.wait_view(
            'TabStripControlButton',
            match=lambda v: v.props.get('TooltipText', '').startswith('New tab'))

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
        tabs = len(self.page_tabs())
        self.browser.quit()
        self.browser.start()
        wait_for(lambda: len(self.page_tabs()) == tabs, what='every tab to be restored')
        # Restored tabs load when shown: each is shown in turn.
        cookies = []
        for page in self.page_tabs():
            page.call('Page.bringToFront')
            cookies.append(self.cookie(page, timeout=60))
        self.assertEqual(sorted(set(cookies)), ['in=default', 'in=personal', 'in=work'])

    def test_4_reopen_closed_tab(self):
        work = self.work_page()
        before = self.pages()
        work.eval(f"window.open({json.dumps(self.url('/other?closed'))}) && 1")
        page = self.new_page(before, '/other?closed')
        wait_for(lambda: page.eval('document.title') == 'other', what='the page')
        self.browser.close_target(page)
        before = self.pages()
        self.browser.key('ctrl+shift+t')
        page = self.new_page(before, '/other?closed')
        wait_for(lambda: page.eval('document.title') == 'other', what='the reopened tab')
        self.assertEqual(self.cookie(page), 'in=work')
        self.browser.close_target(page)

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
        self.browser.close_target(default)
        self.set_pref('containers.traffic_control', [])

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


class ContainersVerticalTabsTest(BrowserTest):
    """Vertical tabs mark container tabs with the same color line."""
    prefs = {'helium': {'browser': {'layout': 2}}}  # Helium's vertical layout

    def tab_views(self):
        """The tabs, top to bottom."""
        return self.browser.wait_settled(
            lambda: sorted((v for v in self.browser.views('TabView') if v.visible),
                           key=lambda v: v.bounds['y']), what='the tabs')

    def line_colors(self, view):
        """The colors along the bottom of a tab, where the line is."""
        b = view.bounds
        bottom = b['y'] + b['height']
        return {self.browser.pixel(b['x'] + b['width'] // 2, y)
                for y in range(bottom - 6, bottom)}

    def test_color_line(self):
        settings = self.browser.new_tab('chrome://settings/containers')
        try:
            wait_for(lambda: settings.eval('!!chrome.settingsPrivate'), what='Settings')
            settings.eval("chrome.settingsPrivate.setPref('containers.new_tab', 'work')")
            icon = (f"{DEEP}('settings-containers-page')?.shadowRoot"
                    "?.querySelector('.container-icon')")
            wait_for(lambda: settings.eval(f'!!{icon}'), what='the containers')
            # Work's color, as Settings shows it: "rgb(r, g, b)".
            work = settings.eval(f"getComputedStyle([...{DEEP}('settings-containers-page')"
                                 ".shadowRoot.querySelectorAll('.container')].find(r => "
                                 "r.textContent.includes('Work')).querySelector('.container-icon'))"
                                 ".backgroundColor")
        finally:
            self.browser.close_target(settings)
        color = tuple(int(n) for n in work[work.index('(') + 1:work.index(')')].split(',')[:3])
        before = len(self.tab_views())
        self.browser.key('ctrl+t')
        wait_for(lambda: len(self.tab_views()) == before + 1, what='the new tab')
        tabs = self.tab_views()
        wait_for(lambda: color in self.line_colors(self.tab_views()[-1]),
                 what="the Work tab's line")
        self.assertNotIn(color, self.line_colors(tabs[0]))


if __name__ == '__main__':
    unittest.main()
