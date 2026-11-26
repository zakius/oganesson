"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/
test_ext_webRequest_requestBody_no_content_type.js.

The add-on's code is Firefox's, as it is. The server's check that the upload
has no Content-Type reads the headers it recorded. Left out as a Gecko
internal: that the console shows no NS_ERROR_NOT_AVAILABLE, Gecko's error
when it read the body of an upload without a Content-Type."""

from extension_test_utils import JS, FirefoxTest


class RequestBodyNoContentTypeTest(FirefoxTest):
    hosts = ('example.com',)
    routes = {'/upload': (200, {}, b'')}

    def test_01_request_body_without_content_type(self):
        url = 'http://example.com/upload'
        body = [0, 42, 255]
        extension = self.load_extension(
            manifest={
                'permissions': ['webRequest', 'http://example.com/'],
            },
            background=JS(r'''function() {
      browser.test.onMessage.addListener(async (url, body) => {
        const requestDetails = new Promise(resolve => {
          browser.webRequest.onBeforeRequest.addListener(
            resolve,
            { urls: [url] },
            ["requestBody"]
          );
        });
        // Wait for the webRequest listener to be registered (bug 1300234).
        await browser.runtime.getPlatformInfo();
        const response = await fetch(url, {
          method: "POST",
          body: new Uint8Array(body),
        });
        const { method, requestBody } = await requestDetails;
        browser.test.sendMessage("upload-complete", {
          status: response.status,
          method,
          formData: requestBody?.formData,
          raw: requestBody?.raw?.flatMap(({ bytes }) =>
            Array.from(new Uint8Array(bytes))
          ),
        });
      });
    }'''))

        extension.startup()
        extension.send_message(url, body)
        result = extension.await_message('upload-complete')
        extension.unload()

        headers = self.server.headers.get('/upload', {})
        self.check(not any(key.lower() == 'content-type' for key in headers),
                   'Upload has no Content-Type')
        self.is_(result.get('status'), 200, 'Server received the upload')
        self.is_(result.get('method'), 'POST', 'webRequest intercepted the upload')
        self.is_(result.get('formData'), None, 'Upload has no parsed form data')
        self.is_(result.get('raw'), body, 'webRequest returns the original bytes')
