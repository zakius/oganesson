"""Port of Firefox's toolkit/components/extensions/test/xpcshell/test_ext_i18n.js.

The add-ons' code is Firefox's, but for the add-on's own URL, which is
`chrome-extension:` for Firefox's `moz-extension:`. Firefox's locale prefs
take this browser's form. `Services.locale.requestedLocales` is the browser's
UI language: the harness starts the browser with `--lang`, so a task that
requests another restarts the browser with it. `intl.accept_languages` is the
profile pref of the same name, set in Settings (`settingsPrivate`).

Firefox's negotiation tasks also mock the languages that Firefox ships
(`Services.locale.availableLocales`), so that it can be in `jp`, `ca-ES` or
`ca-ES-valencia`, a Gecko internal. This browser's UI languages are the ones
it ships, so the port requests only those of Firefox's that it has: `en-US` and
`ca`, where Firefox's test also requests `jp` and the two others. The add-ons
keep all of their locales.

Firefox's content page loads before the add-on starts in every task but the
first, and Firefox runs the add-on's content scripts in it: the port opens it
at the same point.

test_07's text of French and English can't pass here: Chromium's language
detector (CLD3) finds French alone in it, where Firefox's (CLD2) finds both,
with their shares, and the add-on's check then throws. That is the detector's
model, not the API, so it has no step. The task stays, since its first checks
guard the shape of what detectLanguage() gives."""

import json

from extension_test_utils import JS, FirefoxTest
from harness import wait_for

HTML = {'Content-Type': 'text/html'}
FILE_SAMPLE = b"""<!DOCTYPE HTML>

<html>
<head>
<meta charset="utf-8">
</head>
<body>

<div id="test">Sample text</div>

</body>
</html>
"""

I18N_RUN_TESTS = r'''function runTests(assertEq) {
    let _ = browser.i18n.getMessage.bind(browser.i18n);

    let url = browser.runtime.getURL("/");
    assertEq(
      url,
      `chrome-extension://${_("@@extension_id")}/`,
      "@@extension_id builtin message"
    );

    assertEq("Foo.", _("Foo"), "Simple message in selected locale.");

    assertEq("(bar)", _("bar"), "Simple message fallback in default locale.");

    assertEq("", _("some-unknown-locale-string"), "Unknown locale string.");

    assertEq("", _("@@unknown_builtin_string"), "Unknown built-in string.");
    assertEq(
      "",
      _("@@bidi_unknown_builtin_string"),
      "Unknown built-in bidi string."
    );

    assertEq("Føo.", _("Föo"), "Multi-byte message in selected locale.");

    let substitutions = [];
    substitutions[4] = "5";
    substitutions[13] = "14";

    assertEq(
      "'$0' '14' '' '5' '$$$$' '$'.",
      _("basic_substitutions", substitutions),
      "Basic numeric substitutions"
    );

    assertEq(
      "'$0' '' 'just a string' '' '$$$$' '$'.",
      _("basic_substitutions", "just a string"),
      "Basic numeric substitutions, with non-array value"
    );

    let values = _("named_placeholder_substitutions", [
      "(subst $1 $2)",
      "(2 $1 $2)",
    ]).split("\n");

    assertEq(
      "_foo_ (subst $1 $2) _bar_",
      values[0],
      "Named and numeric substitution"
    );

    assertEq(
      "(2 $1 $2)",
      values[1],
      "Numeric substitution amid named placeholders"
    );

    assertEq("$bad name$", values[2], "Named placeholder with invalid key");

    assertEq("", values[3], "Named placeholder with an invalid value");

    assertEq(
      "Accepted, but shouldn't break.",
      values[4],
      "Named placeholder with a strange content value"
    );

    assertEq("$foo", values[5], "Non-placeholder token that should be ignored");
  }'''

# The content script and background of the negotiation and fallback tasks,
# around their runTests().
NEGOTIATION_CONTENT = r'''function (runTestsFn) {
          browser.test.onMessage.addListener(expected => {
            runTestsFn(expected);

            browser.test.sendMessage("content-script-finished");
          });
          browser.test.sendMessage("content-ready");
        }'''
NEGOTIATION_BACKGROUND = r'''function (runTestsFn) {
        browser.test.onMessage.addListener(expected => {
          runTestsFn(expected);

          browser.test.sendMessage("background-script-finished");
        });
      }'''


class I18nTest(FirefoxTest):
    routes = {'/data/file_sample.html': (200, HTML, FILE_SAMPLE)}

    def setUp(self):
        super().setUp()
        self.base_url = self.server.url('/data', host='localhost')

    def request_locale(self, lang):
        """Services.locale.requestedLocales = [lang]: the browser restarts in
        `lang`, its last --lang."""
        self.browser.args = [arg for arg in self.browser.args if not arg.startswith('--lang=')]
        self.browser.args.append(f'--lang={lang}')
        self.restart_browser()

    def set_accept_languages(self, value):
        """Services.prefs.setStringPref("intl.accept_languages", value)."""
        page = self.browser.new_tab('chrome://settings/languages')
        try:
            wait_for(lambda: page.eval('!!chrome.settingsPrivate'), what='Settings')
            page.eval('chrome.settingsPrivate.setPref("intl.accept_languages", '
                      f'{json.dumps(value)}).then(() => 0)')
        finally:
            self.browser.close_target(page)

    def test_01_i18n(self):
        extension = self.load_extension(
            manifest={
                'default_locale': 'jp',

                'content_scripts': [
                    {'matches': ['http://*/*/file_sample.html'], 'js': ['content.js']},
                ],
            },

            files={
                '_locales/en_US/messages.json': {
                    'foo': {
                        'message': 'Foo.',
                        'description': 'foo',
                    },

                    'föo': {
                        'message': 'Føo.',
                        'description': 'foo',
                    },

                    'basic_substitutions': {
                        'message': "'$0' '$14' '$1' '$5' '$$$$$' '$$'.",
                        'description': 'foo',
                    },

                    'Named_placeholder_substitutions': {
                        'message':
                            '$Foo$\n$2\n$bad name$\n$bad_value$\n$bad_content_value$\n$foo',
                        'description': 'foo',
                        'placeholders': {
                            'foO': {
                                'content': '_foo_ $1 _bar_',
                                'description': 'foo',
                            },

                            'bad name': {
                                'content': 'Nope.',
                                'description': 'bad name',
                            },

                            'bad_value': 'Nope.',

                            'bad_content_value': {
                                'content': ["Accepted, but shouldn't break."],
                                'description': 'bad value',
                            },
                        },
                    },

                    'broken_placeholders': {
                        'message': '$broken$',
                        'description': 'broken placeholders',
                        'placeholders': 'foo.',
                    },
                },

                '_locales/jp/messages.json': {
                    'foo': {
                        'message': '(foo)',
                        'description': 'foo',
                    },

                    'bar': {
                        'message': '(bar)',
                        'description': 'bar',
                    },
                },

                'content.js': JS(r'''function (runTestsFn) {
          runTestsFn((...args) => {
            browser.runtime.sendMessage(["assertEq", ...args]);
          });

          browser.runtime.sendMessage(["content-script-finished"]);
        }''', I18N_RUN_TESTS),
            },

            background=JS(r'''function (runTestsFn) {
        browser.runtime.onMessage.addListener(([msg, ...args]) => {
          if (msg == "assertEq") {
            browser.test.assertEq(...args);
          } else {
            browser.test.sendMessage(msg, ...args);
          }
        });

        runTestsFn(browser.test.assertEq.bind(browser.test));
      }''', I18N_RUN_TESTS))

        extension.startup()

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')
        extension.await_message('content-script-finished')
        self.browser.close_target(content_page)

        extension.unload()

    def test_02_extension_id_without_default_locale(self):
        extension = self.load_extension(background=JS(r'''function () {
      browser.test.assertEq(
        location.hostname,
        browser.i18n.getMessage("@@extension_id"),
        "builtin @@extension_id should be available despite no default_locale"
      );
      browser.test.sendMessage("done");
    }'''))
        extension.startup()
        extension.await_message('done')
        extension.unload()

    def negotiate(self, run_tests, files, cases):
        """The negotiation tasks: for each language, an add-on with `files`
        and their runTests(), sent the case's expected results."""
        extension_data = {
            'manifest': {
                'default_locale': 'en_US',

                'content_scripts': [
                    {'matches': ['http://*/*/file_sample.html'], 'js': ['content.js']},
                ],
            },

            'files': {
                **files,
                'content.js': JS(NEGOTIATION_CONTENT, run_tests),
            },

            'background': JS(NEGOTIATION_BACKGROUND, run_tests),
        }

        try:
            for lang, expected in cases:
                self.request_locale(lang)
                content_page = self.open_tab(f'{self.base_url}/file_sample.html')

                extension = self.load_extension(**extension_data)
                extension.startup()
                extension.await_message('content-ready')

                extension.send_message(expected)
                extension.await_message('background-script-finished')
                extension.await_message('content-script-finished')

                extension.unload()
                self.browser.close_target(content_page)
        finally:
            # The next tasks run in Firefox's test locale, as the browser
            # started.
            self.request_locale('en-US')

    def test_03_i18n_negotiation(self):
        run_tests = r'''function runTests(expected) {
    let _ = browser.i18n.getMessage.bind(browser.i18n);

    browser.test.assertEq(expected, _("foo"), "Got expected message");
  }'''
        self.negotiate(run_tests, {
            '_locales/en_US/messages.json': {
                'foo': {
                    'message': 'English.',
                    'description': 'foo',
                },
            },

            '_locales/jp/messages.json': {
                'foo': {
                    'message': '日本語',
                    'description': 'foo',
                },
            },
        }, [('en-US', 'English.')])

    def test_04_i18n_language_fallbacks(self):
        run_tests = r'''function runTests(expected) {
    const _ = browser.i18n.getMessage.bind(browser.i18n);

    const messagesToCompare = ["onlyInCa", "onlyInCaEs", "onlyInCaEsValencia"];

    for (const [index, messageId] of messagesToCompare.entries()) {
      const logMessage = `Got expected ${messageId} message`;
      browser.test.assertEq(expected[index], _(messageId), logMessage);
    }
  }'''
        self.negotiate(run_tests, {
            '_locales/ca-ES-valencia/messages.json': {
                'onlyInCaEsValencia': {
                    'message': 'ca-ES-valencia',
                },
            },

            '_locales/ca_ES/messages.json': {
                'onlyInCaEs': {
                    'message': 'ca-ES',
                },
            },

            '_locales/ca/messages.json': {
                'onlyInCa': {
                    'message': 'ca',
                },
            },

            '_locales/en_US/messages.json': {
                'onlyInCaEsValencia': {
                    'message': 'en-US',
                },
                'onlyInCaEs': {
                    'message': 'en-US',
                },
                'onlyInCa': {
                    'message': 'en-US',
                },
            },
        }, [
            ('ca', ['ca', 'en-US', 'en-US']),
            ('en-US', ['en-US', 'en-US', 'en-US']),
        ])

    def test_05_get_accept_languages(self):
        check_results = r'''function checkResults(source, results, expected) {
    browser.test.assertEq(
      expected.length,
      results.length,
      `got expected number of languages in ${source}`
    );
    results.forEach((lang, index) => {
      browser.test.assertEq(
        expected[index],
        lang,
        `got expected language in ${source}`
      );
    });
  }'''
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    {
                        'matches': ['http://*/*/file_sample.html'],
                        'run_at': 'document_start',
                        'js': ['content_script.js'],
                    },
                ],
            },

            background=JS(r'''function background(checkResultsFn) {
    browser.test.onMessage.addListener(([, expected]) => {
      browser.i18n.getAcceptLanguages().then(results => {
        checkResultsFn("background", results, expected);

        browser.test.sendMessage("background-done");
      });
    });
  }''', check_results),

            files={
                'content_script.js': JS(r'''function content(checkResultsFn) {
    browser.test.onMessage.addListener(([, expected]) => {
      browser.i18n.getAcceptLanguages().then(results => {
        checkResultsFn("contentScript", results, expected);

        browser.test.sendMessage("content-done");
      });
    });
    browser.test.sendMessage("content-loaded");
  }''', check_results),
            })

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.startup()
        extension.await_message('content-loaded')

        expected_langs = ['en-US', 'en']
        extension.send_message(['expect-results', expected_langs])
        extension.await_message('background-done')
        extension.await_message('content-done')

        expected_langs = ['en-US', 'en', 'fr-CA', 'fr']
        self.set_accept_languages(','.join(expected_langs))
        extension.send_message(['expect-results', expected_langs])
        extension.await_message('background-done')
        extension.await_message('content-done')
        self.set_accept_languages('en-US,en')

        self.browser.close_target(content_page)

        extension.unload()

    def test_06_get_ui_language(self):
        get_results = r'''function getResults() {
    return {
      getUILanguage: browser.i18n.getUILanguage(),
      getMessage: browser.i18n.getMessage("@@ui_locale"),
    };
  }'''
        check_results = r'''function checkResults(source, results, expected) {
    browser.test.assertEq(
      expected,
      results.getUILanguage,
      `Got expected getUILanguage result in ${source}`
    );
    browser.test.assertEq(
      expected,
      results.getMessage,
      `Got expected getMessage result in ${source}`
    );
  }'''
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    {
                        'matches': ['http://*/*/file_sample.html'],
                        'run_at': 'document_start',
                        'js': ['content_script.js'],
                    },
                ],
            },

            background=JS(r'''function background(getResultsFn, checkResultsFn) {
    browser.test.onMessage.addListener(([, expected]) => {
      checkResultsFn("background", getResultsFn(), expected);

      browser.test.sendMessage("background-done");
    });
  }''', get_results, check_results),

            files={
                'content_script.js': JS(r'''function content(getResultsFn, checkResultsFn) {
    browser.test.onMessage.addListener(([, expected]) => {
      checkResultsFn("contentScript", getResultsFn(), expected);

      browser.test.sendMessage("content-done");
    });
    browser.test.sendMessage("content-loaded");
  }''', get_results, check_results),
            })

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.startup()
        extension.await_message('content-loaded')

        extension.send_message(['expect-results', 'en-US'])

        extension.await_message('background-done')
        extension.await_message('content-done')

        self.browser.close_target(content_page)

        extension.unload()

    def test_07_detect_language(self):
        af_string = (
            ' aam skukuza die naam beteken hy wat skoonvee of hy wat alles onderstebo keer wysig '
            'bosveldkampe boskampe is kleiner afgeleë ruskampe wat oor min fasiliteite beskik daar is geen restaurante '
            'of winkels nie en slegs oornagbesoekers word toegelaat bateleur')
        # String with intermixed French/English text
        fr_en_string = (
            'France is the largest country in Western Europe and the third-largest in Europe as a whole. '
            'A accès aux chiens et aux frontaux qui lui ont été il peut consulter et modifier ses collections et exporter '
            'Cet article concerne le pays européen aujourd’hui appelé République française. Pour d’autres usages du nom France, '
            'Pour une aide rapide et effective, veuiller trouver votre aide dans le menu ci-dessus.'
            'Motoring events began soon after the construction of the first successful gasoline-fueled automobiles. The quick brown fox jumped over the lazy dog')

        check_result = r'''function checkResult(source, result, expected) {
    browser.test.assertEq(
      expected.isReliable,
      result.isReliable,
      "result.confident is true"
    );
    browser.test.assertEq(
      expected.languages.length,
      result.languages.length,
      `result.languages contains the expected number of languages in ${source}`
    );
    expected.languages.forEach((lang, index) => {
      browser.test.assertEq(
        lang.percentage,
        result.languages[index].percentage,
        `element ${index} of result.languages array has the expected percentage in ${source}`
      );
      browser.test.assertEq(
        lang.language,
        result.languages[index].language,
        `element ${index} of result.languages array has the expected language in ${source}`
      );
    });
  }'''
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    {
                        'matches': ['http://*/*/file_sample.html'],
                        'run_at': 'document_start',
                        'js': ['content_script.js'],
                    },
                ],
            },

            background=JS(r'''function backgroundScript(checkResultFn) {
    browser.test.onMessage.addListener(([msg, expected]) => {
      browser.i18n.detectLanguage(msg).then(result => {
        checkResultFn("background", result, expected);
        browser.test.sendMessage("background-done");
      });
    });
  }''', check_result),

            files={
                'content_script.js': JS(r'''function content(checkResultFn) {
    browser.test.onMessage.addListener(([msg, expected]) => {
      browser.i18n.detectLanguage(msg).then(result => {
        checkResultFn("contentScript", result, expected);
        browser.test.sendMessage("content-done");
      });
    });
    browser.test.sendMessage("content-loaded");
  }''', check_result),
            })

        content_page = self.open_tab(f'{self.base_url}/file_sample.html')

        extension.startup()
        extension.await_message('content-loaded')

        expected = {
            'isReliable': True,
            'languages': [
                {
                    'language': 'fr',
                    'percentage': 67,
                },
                {
                    'language': 'en',
                    'percentage': 32,
                },
            ],
        }
        extension.send_message([fr_en_string, expected])
        extension.await_message('background-done')
        extension.await_message('content-done')

        expected = {
            'isReliable': True,
            'languages': [
                {
                    'language': 'af',
                    'percentage': 99,
                },
            ],
        }
        extension.send_message([af_string, expected])
        extension.await_message('background-done')
        extension.await_message('content-done')

        self.browser.close_target(content_page)

        extension.unload()
