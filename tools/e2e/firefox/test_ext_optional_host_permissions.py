"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_optional_host_permissions.js.

Firefox reads the add-on's optional permissions from Gecko's Extension object
(`manifestOptionalPermissions`). Here they are what the add-on can ask for:
each string of its optional_host_permissions is an optional origin when the
add-on's permissions.request() for it, from a page of the add-on with a user
gesture, shows the prompt and the user's Allow grants it, and an optional API
permission when the same request for it as a permission does. A request for
anything else rejects without a prompt. The page, request.html, is an empty
page added to the add-on for this. The manifest's warnings
(`extension.extension.warnings`) are the add-on's install warnings, which
chrome://extensions shows.

Left out, as a Gecko internal: ExtensionTestUtils.failOnSchemaWarnings(),
which keeps Firefox's test harness from failing on a manifest warning.
"""

import json
import re

from extension_test_utils import FirefoxTest
from harness import wait_for


class OptionalHostPermissionsTest(FirefoxTest):

    def ask(self, page, request):
        """Whether the add-on's permissions.request(`request`) from `page`
        prompts, and the user's Allow grants it. A request that rejects, or
        resolves false, doesn't."""
        page.call('Runtime.evaluate', userGesture=True,
                  expression='globalThis.__fxtestAsked = undefined; '
                             f'chrome.permissions.request({json.dumps(request)})'
                             '.then(granted => globalThis.__fxtestAsked = granted,'
                             ' () => globalThis.__fxtestAsked = false)')

        # The prompt ignores clicks for a moment after it shows (Chromium's
        # InputEventActivationProtector), so Allow is clicked until the
        # request settles.
        def settled():
            if page.eval('globalThis.__fxtestAsked !== undefined', gesture=False):
                return True
            buttons = [view for view in self.browser.views('MdTextButton', Text='Allow')
                       if view.visible]
            if buttons:
                self.browser.click_view(buttons[0])
            return False
        wait_for(settled, interval=0.5, what=f'permissions.request({json.dumps(request)})')
        return page.eval('globalThis.__fxtestAsked', gesture=False)

    def run_test(self, manifest_version=3, optional_host_permissions=None,
                 expect_optional_origins=(), expect_warning=None):
        """Firefox's runTest()."""
        manifest = {'manifest_version': manifest_version}
        if optional_host_permissions is not None:
            manifest['optional_host_permissions'] = optional_host_permissions
        extension = self.load_extension(manifest=manifest,
                                        files={'request.html': '<!DOCTYPE html>'})
        extension.startup()

        warnings = self.browser.extension_info(extension.id)['installWarnings']
        page = self.open_tab(f'chrome-extension://{extension.id}/request.html')
        try:
            candidates = optional_host_permissions or []
            origins = [c for c in candidates if self.ask(page, {'origins': [c]})]
            permissions = [c for c in candidates if self.ask(page, {'permissions': [c]})]
        finally:
            self.browser.close_target(page)

        self.is_(origins, list(expect_optional_origins), 'Expected manifestOptionalPermissions.')
        self.is_(permissions, [], 'Not expecting api permissions.')

        if expect_warning:
            self.check(warnings and re.search(expect_warning, warnings[0]),
                       f'Expected warning. - Actual: {warnings}')
        else:
            self.check(not warnings, f'No warning expected. - Actual: {warnings}')

        extension.unload()

    def test_01_api_permission_ignored(self):
        self.run_test(
            optional_host_permissions=['https://example.com/', 'tabs'],
            expect_optional_origins=['https://example.com/'],
            expect_warning=r'optional_host_permissions.+"tabs" must either: be')

    def test_02_api_permission_all_urls(self):
        self.run_test(
            optional_host_permissions=['<all_urls>'],
            expect_optional_origins=['<all_urls>'])

    def test_03_api_permission_about_urls(self):
        self.run_test(
            optional_host_permissions=['https://example.net/', 'about:*'],
            expect_optional_origins=['https://example.net/'])

    def test_04_api_permission_mv2(self):
        self.run_test(
            manifest_version=2,
            optional_host_permissions=['https://example.org/'],
            expect_optional_origins=[],
            expect_warning=r'"optional_host_permissions" is unsupported in Manifest Version 2')
