"""Port of Firefox's
toolkit/components/extensions/test/xpcshell/test_ext_runtime_getDocumentId.js.

Firefox's server answers /child with an empty response; here it is an empty
HTML page, so that the <iframe>, <embed>, <object> and <frame> load a document,
which the content script runs in, as they do in Firefox. The add-ons' code is
Firefox's, as it is."""

from extension_test_utils import JS, FirefoxTest

HTML = {'Content-Type': 'text/html; charset=utf-8'}


class RuntimeGetDocumentIdTest(FirefoxTest):
    # example.com for the same-origin test, example.net for the cross-origin
    # one.
    hosts = ('example.com', 'example.net')
    routes = {
        '/child': (200, HTML, b''),
        '/iframe_embed_object': (200, HTML, b"""
    <iframe src="http://example.com/child?iframe"></iframe>
    <embed src="http://example.com/child?embed"></embed>
    <object data="http://example.com/child?object"></object>
  """),
    }

    def test_01_getDocumentId_invalid(self):
        extension = self.load_extension(background=JS(r'''function() {
      let proxy = new Proxy(window, {});
      let proto = Object.create(window);

      class FakeFrame extends HTMLIFrameElement {
        constructor() {
          super();
        }
      }
      customElements.define("fake-frame", FakeFrame, { extends: "iframe" });
      let custom = document.createElement("fake-frame");

      let invalid = [null, 13, "blah", document.body, proxy, proto, custom];

      for (let value of invalid) {
        browser.test.assertThrows(
          () => browser.runtime.getDocumentId(value),
          "Invalid argument: target is not a valid window or frame element.",
          "Correct exception thrown."
        );
      }

      let iframe = document.createElement("iframe");
      browser.test.assertThrows(
        () => browser.runtime.getDocumentId(iframe),
        "Could not determine document for target.",
        "getDocumentId throws for detached iframe."
      );

      document.body.append(iframe);

      // Sanity check: we do not always throw, we can get a value.
      browser.test.assertTrue(
        browser.runtime.getDocumentId(iframe),
        "getDocumentId returns ID not when iframe is live."
      );

      let removedWindow = iframe.contentWindow;

      iframe.remove();
      browser.test.assertThrows(
        () => browser.runtime.getDocumentId(iframe),
        "Could not determine document for target.",
        "getDocumentId throws for removed iframe element."
      );
      browser.test.assertThrows(
        () => browser.runtime.getDocumentId(removedWindow),
        "Could not determine document for target.",
        "getDocumentId throws for contentWindow of removed iframe."
      );

      browser.test.sendMessage("done");
    }'''))

        extension.startup()
        extension.await_message('done')
        extension.unload()

    def do_test_getDocumentId_consistent_across_frames(self, is_xorigin):
        """runtime.getDocumentId() takes a window and an iframe, object, embed
        and frameset frame, and gives the same documentId inside and
        outside."""
        extension = self.load_extension(
            manifest={
                'content_scripts': [
                    {
                        'matches': ['*://*/iframe_embed_object'],
                        'js': ['cs_top.js'],
                        'run_at': 'document_start',  # Register onmessage before frame load.
                    },
                    {
                        'matches': ['*://*/child*'],
                        'js': ['cs_frame.js'],
                        'all_frames': True,
                    },
                ],
            },
            files={
                'cs_top.js': JS(r'''function() {
        let receivedMessageCount = 0;
        let seenUUIDs = new Set();
        window.onmessage = e => {
          browser.test.log(`Received message: ${JSON.stringify(e.message)}`);
          ++receivedMessageCount;

          const { tagName } = e.data;
          browser.test.assertEq(
            browser.runtime.getDocumentId(window),
            e.data.topUUID,
            `getDocumentId of top document is same as getDocumentId(parent) inside ${tagName}`
          );

          const elem = document.querySelector(tagName);
          browser.test.assertEq(
            browser.runtime.getDocumentId(elem),
            e.data.frameUUID,
            `getDocumentId on ${tagName} element returns same as script inside`
          );
          // e.source is equivalent to elem.contentWindow for iframe, but not
          // all elements (object/embed) support that, so we use e.source.
          browser.test.assertEq(
            browser.runtime.getDocumentId(e.source),
            e.data.frameUUID,
            `getDocumentId on ${tagName}'s window returns same as script inside`
          );

          seenUUIDs.add(e.data.frameUUID);
          browser.test.assertEq(
            seenUUIDs.size,
            receivedMessageCount,
            "UUID from different documents are unique"
          );

          browser.test.sendMessage(`done:${tagName}`);

          if (receivedMessageCount === 3) {
            // Got all messages from iframe, embed, object. Need to replace
            // body with <frameset>. We could not include this in the main
            // test page because <frameset> is mutually exclusive with <body>.
            let frameset = document.createElement("frameset");
            let frame = document.createElement("frame");
            frame.src = "http://example.com/child?frame";
            frameset.append(frame);
            document.body.replaceWith(frameset);
          }
        };
      }'''),
                'cs_frame.js': JS(r'''function() {
        const tagName = location.search.slice(1);
        const UUID_RE =
          /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
        const frameUUID = browser.runtime.getDocumentId(window);
        browser.test.assertTrue(UUID_RE.test(frameUUID), `UUID in ${tagName}`);

        parent.postMessage(
          {
            tagName,
            frameUUID,
            topUUID: browser.runtime.getDocumentId(parent),
          },
          "*"
        );
      }'''),
            })

        extension.startup()

        base_url = 'http://example.net' if is_xorigin else 'http://example.com'
        content_page = self.open_tab(f'{base_url}/iframe_embed_object')
        for tag_name in ('iframe', 'embed', 'object', 'frame'):
            extension.await_message(f'done:{tag_name}')
        self.browser.close_target(content_page)

        extension.unload()

    def test_02_getDocumentId_same_origin_frames(self):
        self.do_test_getDocumentId_consistent_across_frames(is_xorigin=False)

    def test_03_getDocumentId_cross_origin_frames(self):
        self.do_test_getDocumentId_consistent_across_frames(is_xorigin=True)
