"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_background_script_and_service_worker.js.

Firefox's `WebExtensionPolicy.backgroundServiceWorkerEnabled` takes this
browser's form: it runs extension service workers, so the tasks that Firefox
skips without them run, and where Firefox's expected background type depends
on it, the port expects the one Firefox gives with them. Firefox's manifest warnings (`extension.warnings`) are the
add-on's install warnings that chrome://extensions shows.
"""

from extension_test_utils import JS, FirefoxTest


class BackgroundScriptAndServiceWorkerTest(FirefoxTest):

    def extension_with_background(self, with_scripts=False, with_service_worker=False,
                                  with_page=False, with_preferred_environment=None,
                                  expected_background_type=None,
                                  expected_manifest_warnings=()):
        background = {}
        if with_scripts:
            background['scripts'] = ['scripts.js']
        if with_service_worker:
            background['service_worker'] = 'sw.js'
        if with_page:
            background['page'] = 'page.html'
        if with_preferred_environment:
            background['preferred_environment'] = with_preferred_environment
        extension = self.load_extension(
            manifest={'background': background},
            files={
                'scripts.js': JS('''() => {
                  browser.test.sendMessage("from_bg", "scripts");
                }'''),
                'sw.js': JS('''() => {
                  browser.test.sendMessage("from_bg", "service_worker");
                }'''),
                'page.html': '<!DOCTYPE html><script src="page.js"></script>',
                'page.js': JS('''() => {
                  browser.test.sendMessage("from_bg", "page");
                }'''),
            })
        extension.startup()

        # Waiting for background to start
        self.is_(extension.await_message('from_bg'), expected_background_type,
                 'Expected background type')

        self.is_(self.browser.extension_info(extension.id)['installWarnings'],
                 list(expected_manifest_warnings), 'Expected manifest warnings')

        extension.unload()

    def test_01_page_and_scripts(self):
        self.extension_with_background(
            with_page=True,
            with_scripts=True,
            # Should be expected_background_type: "scripts", not "page".
            # https://github.com/w3c/webextensions/issues/282#issuecomment-1443332913
            # ... but changing that may potentially affect backcompat of existing
            # Firefox add-ons.
            expected_background_type='page',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background: Both background.page and background.scripts specified. background.scripts will be ignored.',
            ])

    def test_02_service_worker_and_document(self):
        self.extension_with_background(
            with_service_worker=True,
            expected_background_type='service_worker',
            expected_manifest_warnings=[])
        self.extension_with_background(
            with_scripts=True,
            with_service_worker=True,
            expected_background_type='scripts',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background: with both background.service_worker and background.scripts, only background.scripts will be loaded. This can be changed with background.preferred_environment.',
            ])
        self.extension_with_background(
            with_page=True,
            with_service_worker=True,
            expected_background_type='page',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background: with both background.service_worker and background.page, only background.page will be loaded. This can be changed with background.preferred_environment.',
            ])
        self.extension_with_background(
            with_page=True,
            with_scripts=True,
            with_service_worker=True,
            expected_background_type='page',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background: Both background.page and background.scripts specified. background.scripts will be ignored.',
                'Reading manifest: Warning processing background: with both background.service_worker and background.page, only background.page will be loaded. This can be changed with background.preferred_environment.',
            ])

    def test_03_preferred_environment(self):
        self.extension_with_background(
            with_scripts=True,
            with_service_worker=True,
            with_preferred_environment=['document'],
            expected_background_type='scripts')
        self.extension_with_background(
            with_scripts=True,
            with_preferred_environment=['service_worker'],
            expected_background_type='scripts')
        self.extension_with_background(
            with_page=True,
            with_service_worker=True,
            with_preferred_environment=['document', 'service_worker'],
            expected_background_type='page')
        self.extension_with_background(
            with_page=True,
            with_service_worker=True,
            with_preferred_environment=['service_worker'],
            expected_background_type='service_worker',
            expected_manifest_warnings=[])
        self.extension_with_background(
            with_scripts=True,
            with_service_worker=True,
            with_preferred_environment=['service_worker'],
            expected_background_type='service_worker',
            expected_manifest_warnings=[])

    def test_04_preferred_environment_unrecognized(self):
        self.extension_with_background(
            with_scripts=True,
            with_service_worker=True,
            # "page" and "scripts" are ignored (it should be "document"), so only
            # "service_worker" is recognized.
            with_preferred_environment=['page', 'scripts', 'service_worker'],
            # If "service_worker" is recognized and supported, use it. Otherwise we
            # default to the background page (in "scripts"), since it is the only
            # specified entry that is supported.
            expected_background_type='service_worker',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background.preferred_environment: Error processing background.preferred_environment.0: Invalid enumeration value "page"',
                'Reading manifest: Warning processing background.preferred_environment: Error processing background.preferred_environment.1: Invalid enumeration value "scripts"',
            ])
        self.extension_with_background(
            with_page=True,
            with_service_worker=True,
            # All of these are invalid (only "service_worker" is recognized").
            with_preferred_environment=['serviceWorker', 'serviceworker', 'worker'],
            # Since there is no valid preferred_environment entry, we pick the default,
            # i.e. "page".
            expected_background_type='page',
            expected_manifest_warnings=[
                'Reading manifest: Warning processing background.preferred_environment: Error processing background.preferred_environment.0: Invalid enumeration value "serviceWorker"',
                'Reading manifest: Warning processing background.preferred_environment: Error processing background.preferred_environment.1: Invalid enumeration value "serviceworker"',
                'Reading manifest: Warning processing background.preferred_environment: Error processing background.preferred_environment.2: Invalid enumeration value "worker"',
            ])

    def test_05_preferred_environment_when_sw_enabled(self):
        self.extension_with_background(
            with_service_worker=True,
            with_preferred_environment=['document', 'service_worker'],
            expected_background_type='service_worker')
        self.extension_with_background(
            with_service_worker=True,
            with_preferred_environment=['document'],
            expected_background_type='service_worker')
