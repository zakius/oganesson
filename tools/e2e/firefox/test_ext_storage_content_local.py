"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_storage_content_local.js.

The add-ons' code is Firefox's, as it is. Firefox runs each task on each of
its two storage.local backends, a JSON file and IndexedDB, which its pref
extensions.webextensions.ExtensionStorageIDB.enabled picks. This browser has
one backend, so the two tasks of each pair run the same checks on it. Left
out: PromiseTestUtils.allowMatchingRejectionsGlobally(), which lets a
rejection pass in Firefox's test harness; it checks nothing. Of
head_storage.js, see head_storage.py."""

from firefox import head_storage
from extension_test_utils import FirefoxTest

# Firefox's toolkit/components/extensions/test/xpcshell/data/file_sample.html
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


class StorageContentLocalTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/data/file_sample.html': (200, {'Content-Type': 'text/html'}, FILE_SAMPLE)}

    def test_01_contentscript_storage_local_file_backend(self):
        head_storage.test_contentscript_storage(self, 'local')

    def test_02_contentscript_storage_local_idb_backend(self):
        head_storage.test_contentscript_storage(self, 'local')

    def test_03_contentscript_storage_local_file_getBytesInUse(self):
        head_storage.test_contentscript_storage_area_getBytesInUse(self, 'local')

    def test_04_contentscript_storage_local_idb_getBytesInUse(self):
        head_storage.test_contentscript_storage_area_getBytesInUse(self, 'local')
