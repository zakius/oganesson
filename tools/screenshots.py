#!/usr/bin/env python3
"""Screenshots of oganesson for dubna's site. Each scene starts the browser on
its own Xvfb display (tools/e2e/harness.py) with a throwaway profile set up to
show a feature, and saves the browser window as OUT/<scene>.webp. Pages come
from the network (Wikipedia), so run it online.

Usage: OGANESSON_BINARY=/opt/oganesson/oganesson tools/screenshots.py OUT [SCENE...]
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'e2e'))
import harness  # noqa: E402

# On theme: the elements the browsers are named after, and the town.
TABS = ['https://en.wikipedia.org/wiki/Oganesson', 'https://en.wikipedia.org/wiki/Tennessine',
        'https://en.wikipedia.org/wiki/Dubna', 'https://en.wikipedia.org/wiki/Helium']
DARK = ['--force-dark-mode']
# Strokes, a rocker and the wheel, as someone might set them up (chrome_command_ids.h).
IDC_BACK, IDC_FORWARD, IDC_RELOAD = 33000, 33001, 33002
IDC_NEW_TAB, IDC_CLOSE_TAB, IDC_SELECT_NEXT_TAB, IDC_SELECT_PREVIOUS_TAB = 34014, 34015, 34016, 34017
IDC_RESTORE_TAB = 34028
GESTURES = {'oganesson': {'mouse_gestures': {
    'L': IDC_BACK, 'R': IDC_FORWARD, 'UD': IDC_RELOAD, 'D': IDC_NEW_TAB, 'DR': IDC_CLOSE_TAB,
    'UL': IDC_RESTORE_TAB, 'rocker-rl': IDC_BACK, 'rocker-lr': IDC_FORWARD,
    'wheel-down': IDC_SELECT_NEXT_TAB, 'wheel-up': IDC_SELECT_PREVIOUS_TAB}}}


def open_tabs(browser, urls):
    """Opens URLS in new tabs, shows the first and closes the starting tab, whose
    new tab page would keep the address bar focused."""
    # Wikipedia's own dark theme, to go with the browser's.
    browser.browser_call('Storage.setCookies', cookies=[
        {'name': 'enwikimwclientpreferences', 'value': 'skin-theme-clientpref-night',
         'domain': '.wikipedia.org', 'path': '/'}])
    start = [t for t in browser.targets() if t['type'] == 'page']
    pages = [browser.new_tab(url) for url in urls]
    for target in start:
        browser._get(f'/json/close/{target["id"]}')
    browser._get(f'/json/activate/{pages[0].id}')
    time.sleep(4)  # pages and favicons
    return pages[0]


# Scrolls the settings section whose heading is TEXT into view, through the
# settings pages' shadow roots.
SCROLL_TO = """(() => {
  const find = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { const hit = find(el.shadowRoot); if (hit) return hit; }
      if (!el.children.length && el.textContent.trim() === %r) return el;
    }
  };
  const el = find(document);
  if (el) el.scrollIntoView({block: 'start'});
  return !!el;
})()"""


def capture(browser, out):
    # The pointer starts over the first tab, where it would show hover effects.
    browser.xdotool('mousemove', str(harness.WINDOW[0] - 10), str(harness.WINDOW[1] - 10))
    time.sleep(0.5)
    png = subprocess.run(['import', '-display', browser.xvfb.display, '-window', 'root',
                          '-crop', f'{harness.WINDOW[0]}x{harness.WINDOW[1]}+0+0', 'png:-'],
                         check=True, capture_output=True).stdout
    subprocess.run(['magick', 'png:-', '-quality', '86', str(out)], input=png, check=True)


def tabs(out):
    """The classic layout with the tab close buttons hidden and uBlock Origin's
    button moved to the left of the address bar."""
    browser = harness.Browser(args=DARK + ['--hide-tab-close-buttons'], prefs={'oganesson': {
        'toolbar': {'items': ['back', 'forward', 'reload', f'extension:{harness.UBO}',
                              'location_bar', 'extensions', 'avatar', 'app_menu']}}})
    try:
        open_tabs(browser, TABS)
        capture(browser, out)
    finally:
        browser.stop()


def vertical(out):
    """Helium's vertical layout, with the tabs on the right."""
    browser = harness.Browser(args=DARK, prefs={'helium': {'browser': {
        'layout': 2, 'vertical_right_aligned': True}}})
    try:
        open_tabs(browser, TABS)
        capture(browser, out)
    finally:
        browser.stop()


# Clicks the button labeled BUTTON in the settings row labeled ROW.
CLICK_IN_ROW = """(() => {
  const deep = (root, out = []) => {
    for (const el of root.querySelectorAll('*')) {
      out.push(el);
      if (el.shadowRoot) deep(el.shadowRoot, out);
    }
    return out;
  };
  const label = deep(document).find(el => !el.children.length && el.textContent.trim() === %r);
  for (let row = label; row; row = row.parentNode || row.host) {
    if (!row.querySelectorAll) continue;
    const button = deep(row).find(el => /BUTTON/.test(el.tagName) && el.textContent.trim() === %r);
    if (button) { button.click(); return true; }
  }
  return false;
})()"""
# Focuses the first text field in an open settings dialog.
FOCUS_DIALOG_INPUT = """(() => {
  const deep = (root, out = []) => {
    for (const el of root.querySelectorAll('*')) {
      out.push(el);
      if (el.shadowRoot) deep(el.shadowRoot, out);
    }
    return out;
  };
  const inDialog = (el) => {
    for (; el; el = el.parentNode || el.host)
      if ((el.tagName === 'DIALOG' || el.tagName === 'CR-DIALOG') && el.open) return true;
    return false;
  };
  const input = deep(document).find(el => el.tagName === 'INPUT' && inDialog(el));
  if (input) input.focus();
  return !!input;
})()"""
# Settings focuses its search field on load; a screenshot shouldn't show it.
BLUR = """(() => {
  let el = document.activeElement;
  while (el && el.shadowRoot && el.shadowRoot.activeElement) el = el.shadowRoot.activeElement;
  if (el) el.blur();
})()"""


def settings_page(out, url, section=None, prefs=None, click=None, type_text=None):
    browser = harness.Browser(args=DARK, prefs=prefs)
    try:
        page = open_tabs(browser, [url])
        if section and not page.eval(SCROLL_TO % section):
            sys.exit(f'screenshots: no {section!r} on {url}')
        time.sleep(1)
        page.eval(BLUR)
        if click:
            if not page.eval(CLICK_IN_ROW % click):
                sys.exit(f'screenshots: no {click[1]!r} in {click[0]!r} on {url}')
            time.sleep(1)
            if type_text:
                if not page.eval(FOCUS_DIALOG_INPUT):
                    sys.exit(f'screenshots: no text field in the dialog on {url}')
                browser.xdotool('type', '--delay', '80', type_text)
        time.sleep(0.5)
        capture(browser, out)
    finally:
        browser.stop()


SCENES = {
    'tabs': tabs,
    'vertical': vertical,
    'tab-behavior': lambda out: settings_page(out, 'chrome://settings/appearance', 'Behavior'),
    'gestures': lambda out: settings_page(out, 'chrome://settings/system/shortcuts',
                                          section='Back', prefs=GESTURES,
                                          click=('Close other tabs', 'Add gesture'),
                                          type_text='UR'),
}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[2:] or SCENES:
        SCENES[name](out / f'{name}.webp')
        print(out / f'{name}.webp')


if __name__ == '__main__':
    main()
