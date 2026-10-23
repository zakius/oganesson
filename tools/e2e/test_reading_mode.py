"""Reading mode (oganesson/core/reading-mode.patch).

The page menu's "Open in reading mode" opens the side panel with the page's
article, distilled by Readability, without the page's navigation and sidebar.
"""

import unittest

from harness import BrowserTest, Server, wait_for

ARTICLE = ' '.join(['The noble gases sit in the last group of the periodic table.'] * 8)
PAGE = f'''<!doctype html><title>Oganesson</title>
<nav><a href="/">NAVIGATION-JUNK</a></nav>
<aside>SIDEBAR-JUNK</aside>
<article><h1>Oganesson</h1>
{''.join(f'<p id=p{i}>Paragraph {i}. {ARTICLE}</p>' for i in range(6))}
</article>'''.encode()

# The panel's text, through its shadow roots.
PANEL_TEXT = '''(() => {
  const text = node => [...(node.shadowRoot ? node.shadowRoot.childNodes : []),
                         ...node.childNodes]
      .map(n => n.nodeType === Node.TEXT_NODE ? n.textContent : text(n)).join(' ');
  return text(document.body);
})()'''


class ReadingModeTest(BrowserTest):

    @classmethod
    def setUpClass(cls):
        cls.server = Server({'/article': (200, {'Content-Type': 'text/html'}, PAGE)})
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def test_page_menu_opens_readability_article(self):
        page = self.browser.new_tab(self.server.url('/article'))
        self.browser.wait_view('ContentsWebView')
        wait_for(lambda: page.eval('!!document.querySelector("#p2")'), what='the article')
        self.browser.click_element(page, '#p2', button=3)
        item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                      for i in group
                                      if i['Title'].replace('&', '') == 'Open in reading mode'),
                                     None),
                        what='"Open in reading mode"')
        self.browser.click_view(item)
        panel = self.browser.page('read-anything')
        text = wait_for(lambda: (lambda t: t if 'Paragraph 5.' in t else None)(
            panel.eval(PANEL_TEXT)), timeout=30, what='the article in reading mode')
        self.assertIn('Paragraph 0.', text)
        self.assertNotIn('NAVIGATION-JUNK', text)
        self.assertNotIn('SIDEBAR-JUNK', text)
        self.assertEqual(panel.eval('chrome.readingMode.activeDistillationMethod'),
                         panel.eval('chrome.readingMode.distillationTypeReadability'))


if __name__ == '__main__':
    unittest.main()
