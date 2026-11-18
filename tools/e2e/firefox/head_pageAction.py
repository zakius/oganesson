"""Firefox's browser/components/extensions/test/browser/head_pageAction.js:
runTests(), which the ports of Firefox's pageAction context and title tests
share.

The add-on's background is Firefox's, as it is. It runs the test's steps,
and after each one it checks what pageAction's getters give. Then Firefox
checks the page action's button in the location bar (checkDetails()), which
this browser doesn't have yet (zakius/oganesson#68, head.page_action_button()):
a step that expects the page action hidden passes that check, and a step that
expects it shown fails it. Firefox also waits for the button to change
(waitForDetails()) and compares its icon, tooltip and accessible name with
the step's: those checks wait for the button too. Then the add-on runs its
steps again in a new window.

Firefox requests the locale `es-ES` while the add-on runs: this browser takes
it as its UI language (--lang), so the browser restarts before the add-on
loads, and again when the test ends. Left out: the mocked
`Services.locale.availableLocales`, the languages Firefox ships, a Gecko
internal.
"""

from firefox import head
from extension_test_utils import JS

BACKGROUND = r'''function background(getTests) {
  let tests;

  // Gets the current details of the page action, and returns a
  // promise that resolves to an object containing them.
  async function getDetails(tabId) {
    return {
      title: await browser.pageAction.getTitle({ tabId }),
      popup: await browser.pageAction.getPopup({ tabId }),
      isShown: await browser.pageAction.isShown({ tabId }),
    };
  }

  // Runs the next test in the `tests` array, checks the results,
  // and passes control back to the outer test scope.
  function nextTest() {
    let test = tests.shift();

    test(async expecting => {
      let [tab] = await browser.tabs.query({
        active: true,
        currentWindow: true,
      });
      let { id: tabId, windowId, url } = tab;

      browser.test.log(`Get details: tab={id: ${tabId}, url: ${url}}`);

      // Check that the API returns the expected values, and then
      // run the next test.
      let details = await getDetails(tabId);
      if (expecting) {
        browser.test.assertEq(
          expecting.title,
          details.title,
          "expected value from getTitle"
        );

        browser.test.assertEq(
          expecting.popup,
          details.popup,
          "expected value from getPopup"
        );
      }

      browser.test.assertEq(
        !!expecting,
        details.isShown,
        "expected value from isShown"
      );

      // Check that the actual icon has the expected values, then
      // run the next test.
      browser.test.sendMessage("nextTest", expecting, windowId, tests.length);
    });
  }

  async function runTests() {
    let tabs = [];
    let windows = [];
    tests = getTests(tabs, windows);

    let resultTabs = await browser.tabs.query({
      active: true,
      currentWindow: true,
    });

    tabs[0] = resultTabs[0].id;
    windows[0] = resultTabs[0].windowId;

    nextTest();
  }

  browser.test.onMessage.addListener(msg => {
    if (msg == "runTests") {
      runTests();
    } else if (msg == "runNextTest") {
      nextTest();
    } else {
      browser.test.fail(`Unexpected message: ${msg}`);
    }
  });

  runTests();
}'''


def request_locale(test, lang):
    """Services.locale.requestedLocales = [lang]: the browser restarts in
    `lang`, its last --lang."""
    test.browser.args = [arg for arg in test.browser.args if not arg.startswith('--lang=')]
    test.browser.args.append(f'--lang={lang}')
    test.restart_browser()


def check_details(test, extension, details):
    """checkDetails(): the add-on's page action button is hidden when the
    step expects no details, and is there when it expects some."""
    button = head.page_action_button(test, extension)
    if details is None:
        test.check(button is None, 'image is disabled')
    else:
        test.check(button is not None, 'image exists')


def run_tests(test, manifest, files, get_tests):
    """runTests(): the add-on with `manifest` and `files` runs the steps of
    `get_tests`, the source of Firefox's getTests function, in the first
    window and then in a new one."""
    extension = test.load_extension(manifest=manifest, files=files,
                                    background=JS(BACKGROUND, get_tests))
    steps = []
    extension.on_message('nextTest', lambda *args: steps.append(args))

    def next_step():
        if steps:
            return steps.pop(0)
        return None

    windows = []
    test_new_windows = 1
    request_locale(test, 'es-ES')
    test.addCleanup(request_locale, test, 'en-US')
    extension.startup()
    while True:
        # Firefox reads the button in the window of `window_id`.
        expecting, window_id, tests_remaining = test.wait_reports(next_step, 'the next test')
        check_details(test, extension, expecting)
        if tests_remaining:
            extension.send_message('runNextTest')
        elif test_new_windows:
            test_new_windows -= 1
            windows.append(head.open_new_browser_window(test))
            extension.send_message('runTests')
        else:
            break

    extension.unload()

    test.check(head.page_action_button(test, extension) is None,
               'pageAction image removed from document')
    for window in windows:
        test.check(head.page_action_button(test, extension) is None,
                   'pageAction image removed from second document')
        head.close_window(test, window)
