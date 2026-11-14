"""Opt-in page translation (oganesson/core/translation.patch,
docs/translation.md).

Off by default: a German page has no "Translate to English" item, pages can't
use the Translator API, and the browser contacts no translate host and doesn't
check TranslateKit's components for updates. Settings > Languages >
Translation turns it on and picks the engine. With Google Translate, the page
text goes to Google's keyless endpoint and comes back translated. On this
device, TranslateKit translates it: Chromium's stand-in library, built with
the browser, which prefixes each text with its language pack's dict.dat.
Without the stand-in, translating first asks to download the languages, and
only a yes makes the component updater ask Google for TranslateKit.

--host-resolver-rules sends Google's translate and update hosts to local HTTPS
servers, which record what they get.
"""

import json
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

from harness import BINARY, BrowserTest, Server, wait_for
from test_browser_traffic import NO_UPDATE, certificate
from test_firefox_sync import FIND

TRANSLATE_HOST = 'translate.googleapis.com'
TRANSLATE_PATH = '/translate_a/t'
UPDATE_HOST = 'update.googleapis.com'
UPDATE_PATH = '/service/update2/json'
# TranslateKit's library and its German-English pack.
TRANSLATE_KIT = 'lbimbicckdokpoicboneldipejkhjgdg'
GERMAN_PACK = 'nhffhdkoepefheklonindbljcknflfij'
MOCK_LIBRARY = BINARY.parent / 'libmock_translate_kit_lib.so'

GERMAN = 'Guten Morgen. Heute ist ein schöner Tag.'
PAGE = ('<!doctype html><html lang="de"><meta charset="utf-8"><title>Seite</title><body>'
        f'<p id="text">{GERMAN}</p>').encode()
# The menu's title, with its accelerator.
ITEM = '&Translate to English'
AVAILABILITY = ("Translator.availability({sourceLanguage: 'de', targetLanguage: 'en'})"
                ".catch(e => e.name)")


def translate_reply(server):
    """Google's reply: each text with "[google] " before it."""
    def reply(headers):
        form = urllib.parse.parse_qs(server.bodies[TRANSLATE_PATH].decode())
        return (200, {'Content-Type': 'application/json'},
                json.dumps([f'[google] {text}' for text in form['q']]).encode())
    return reply


def local_state(engine):
    return {'oganesson': {'translate': {'enabled': True, 'engine': engine}}}


class TranslationTest(BrowserTest):
    """A German page, and Google's translate and update hosts."""

    @classmethod
    def extra_args(cls):
        return ()

    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix='oganesson-translation-'))
        (cls.folder / 'translate').mkdir()
        (cls.folder / 'update').mkdir()
        cls.google = Server({}, tls=certificate(cls.folder / 'translate', TRANSLATE_HOST))
        cls.google.routes[TRANSLATE_PATH] = translate_reply(cls.google)
        cls.update = Server({UPDATE_PATH: (200, {'Content-Type': 'application/json'}, NO_UPDATE)},
                            tls=certificate(cls.folder / 'update', UPDATE_HOST))
        cls.site = Server({'/de.html': (200, {'Content-Type': 'text/html; charset=utf-8'}, PAGE)})
        cls.browser_args = (
            f'--host-resolver-rules=MAP {TRANSLATE_HOST} 127.0.0.1:{cls.google.port},'
            f' MAP {UPDATE_HOST} 127.0.0.1:{cls.update.port}',
            '--ignore-certificate-errors', '--component-updater=fast-update',
            *cls.extra_args())
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for server in (cls.google, cls.update, cls.site):
            server.stop()

    def open_page(self):
        page = self.browser.new_tab(self.site.url('/de.html'))
        wait_for(lambda: page.eval("document.readyState == 'complete'"
                                   " && !!document.getElementById('text')"),
                 what='the German page')
        page.call('Page.bringToFront')
        return page

    def page_menu(self, page):
        """The titles of the page's context menu, closed again."""
        self.browser.click_element(page, '#text', button=3)
        wait_for(self.browser.menus, what='the context menu')
        titles = [i['Title'] for menu in self.browser.menus() for group in menu for i in group]
        self.browser.key('Escape')
        wait_for(lambda: not self.browser.menus(), what='the menu to close')
        return titles

    def translate(self, page):
        """Chooses "Translate to English" once language detection offers it."""
        wait_for(lambda: ITEM in self.page_menu(page), what='the Translate item')
        self.browser.click_element(page, '#text', button=3)
        item = wait_for(lambda: next((i for menu in self.browser.menus() for group in menu
                                      for i in group if i['Title'] == ITEM), None),
                        what='the Translate item')
        self.browser.click_view(item)
        wait_for(lambda: not self.browser.menus(), what='the menu to close')

    def text(self, page):
        return page.eval("document.getElementById('text').innerText")

    def translate_kit_checks(self):
        return [body for body in self.update.posts if TRANSLATE_KIT.encode() in body]


class OffTest(TranslationTest):

    def test_off_by_default(self):
        page = self.open_page()
        try:
            time.sleep(3)  # language detection, after the load
            self.assertNotIn(ITEM, self.page_menu(page))
            self.assertEqual(page.eval(AVAILABILITY), 'unavailable')
        finally:
            self.browser.close_target(page)

        settings = self.browser.new_tab('chrome://settings/languages')
        toggle = f"({FIND})('settings-translate-page')?.shadowRoot?.querySelector('#translatePages')"
        wait_for(lambda: settings.eval(f'!!{toggle}'), what='the switch')
        self.assertEqual(settings.eval(f'{toggle}.label'), 'Translate pages')
        self.assertIs(settings.eval(f'{toggle}.checked'), False)
        self.browser.close_target(settings)

        # Long enough for the component updater's first check (fast-update).
        wait_for(lambda: self.update.posts, timeout=120, what="the certificates' update check")
        self.assertEqual(self.google.requests, [])
        self.assertEqual(self.translate_kit_checks(), [])

    def test_switch_and_engine(self):
        settings = self.browser.new_tab('chrome://settings/languages')
        page = f"({FIND})('settings-translate-page')?.shadowRoot"
        wait_for(lambda: settings.eval(f'!!{page}?.querySelector("#translatePages")'),
                 what='the switch')
        self.assertIs(settings.eval(f'{page}.querySelector("cr-collapse").opened'), False)
        settings.eval(f'{page}.querySelector("#translatePages").click()')
        wait_for(lambda: settings.eval(f'{page}.querySelector("cr-collapse").opened'),
                 what='the engines to show')
        settings.eval(f'{page}.querySelector("controlled-radio-button[name=google]").click()')
        get = "chrome.settingsPrivate.getPref('{}').then(p => p.value)"
        wait_for(lambda: settings.eval(get.format('oganesson.translate.engine')) == 'google',
                 what='the engine pref')
        self.assertIs(settings.eval(get.format('oganesson.translate.enabled')), True)
        self.browser.close_target(settings)

        page = self.open_page()
        try:
            self.assertEqual(self.text(page), GERMAN)
            self.translate(page)
            wait_for(lambda: self.text(page) == f'[google] {GERMAN}', what='the translation')
        finally:
            self.browser.close_target(page)


class GoogleTest(TranslationTest):
    local_state = local_state('google')

    def test_translates_through_google(self):
        page = self.open_page()
        try:
            # Only on-device translation lets pages use the Translator API.
            self.assertEqual(page.eval(AVAILABILITY), 'unavailable')
            self.translate(page)
            wait_for(lambda: self.text(page) == f'[google] {GERMAN}', what='the translation')
            headers = self.google.headers[TRANSLATE_PATH]
            self.assertNotIn('Cookie', headers)
            form = urllib.parse.parse_qs(self.google.bodies[TRANSLATE_PATH].decode())
            self.assertIn(GERMAN, form['q'])
            self.assertEqual(self.translate_kit_checks(), [])
        finally:
            self.browser.close_target(page)


# Chromium's record of TranslateKit and its German pack registered by an
# earlier run: it registers them again at startup.
REGISTERED = {'on_device_translation': {
    'translate_kit_registered': True,
    'translate_kit_packages': {'de_en_registered': True}}}


class RegisteredOffTest(TranslationTest):
    """Off, TranslateKit registered by an earlier run never checks."""
    local_state = REGISTERED

    def test_no_check(self):
        # Long enough for the component updater's first checks (fast-update).
        wait_for(lambda: self.update.posts, timeout=120, what="the certificates' update check")
        time.sleep(15)
        self.assertEqual(self.translate_kit_checks(), [])
        self.assertNotIn(GERMAN_PACK.encode(), b''.join(self.update.posts))


class RegisteredOnTest(TranslationTest):
    """On this device, TranslateKit registered by an earlier run checks for
    updates with the automatic checks."""
    local_state = {**REGISTERED, **local_state('device')}

    def test_checks(self):
        wait_for(self.translate_kit_checks, timeout=120, what="TranslateKit's update check")
        self.assertIn(GERMAN_PACK.encode(), b''.join(self.translate_kit_checks()))


@unittest.skipUnless(MOCK_LIBRARY.exists(), f'no {MOCK_LIBRARY.name} next to the binary')
class OnDeviceTest(TranslationTest):
    """TranslateKit's stand-in, with a German-English pack given on the
    command line, so nothing downloads."""
    local_state = local_state('device')

    @classmethod
    def extra_args(cls):
        pack = Path(tempfile.mkdtemp(prefix='oganesson-translate-kit-'))
        (pack / 'dict.dat').write_text('[device] ')
        return (f'--translate-kit-binary-path={MOCK_LIBRARY}',
                f'--translate-kit-packages=de,en,{pack}')

    def test_translates_on_device(self):
        page = self.open_page()
        try:
            self.assertNotEqual(page.eval(AVAILABILITY), 'unavailable')
            self.translate(page)
            wait_for(lambda: self.text(page) == f'[device] {GERMAN}', what='the translation')
            self.assertEqual(self.google.requests, [])
        finally:
            self.browser.close_target(page)


class DownloadTest(TranslationTest):
    """On this device, without TranslateKit: translating asks first."""
    local_state = local_state('device')

    def answer(self, label):
        """Clicks `label` in the question, and returns its text."""
        button = wait_for(lambda: next((v for v in self.browser.views('MdTextButton')
                                        if v.visible and v['Text'] == label), None),
                          what='the download question')
        text = ' '.join(v['Text'] for v in self.browser.views('Label') if v.visible)
        # A dialog's buttons take a click only once the pointer rests on them.
        self.browser.xdotool('mousemove', *map(str, button.center))
        time.sleep(0.5)
        self.browser.xdotool('click', '1')
        wait_for(lambda: not any(v.visible for v in self.browser.views('MessageBoxView')),
                 what='the question to close')
        return text

    def test_asks_before_downloading(self):
        page = self.open_page()
        try:
            self.translate(page)
            text = self.answer('Cancel')
            self.assertIn('German', text)
            time.sleep(5)
            self.assertEqual(self.translate_kit_checks(), [])
            self.assertEqual(self.text(page), GERMAN)

            self.translate(page)
            self.answer('Yes')
            wait_for(self.translate_kit_checks, timeout=60, what="TranslateKit's update check")
            checks = b''.join(self.translate_kit_checks())
            self.assertIn(GERMAN_PACK.encode(), b''.join(self.update.posts))
            self.assertIn(TRANSLATE_KIT.encode(), checks)
            self.assertEqual(self.google.requests, [])
        finally:
            self.browser.close_target(page)


if __name__ == '__main__':
    unittest.main()
