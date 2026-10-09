# Firefox Sync

The browser's C++ adapters connect Chromium's password, bookmark, history, tab, and autofill stores to `rust/oganesson_sync`. The Rust library uses pinned Mozilla application-services crates for account and Sync protocols. It loads beside the browser as `liboganesson_sync.so`.

The retained implementation uses OAuth with PKCE, encrypts saved account secrets through Chromium's OS cryptography service, and routes HTTP through the profile's network context. Signing out discards pending results. The client must honor server backoff and preserve local edits made during a sync.

Supported implementation scope: passwords, bookmarks, history, open tabs, addresses, and payment methods. Bookmark keywords and separators stay in the Sync store (places) only: the browser never sees them, and Sync keeps them in place for Firefox. Container synchronization is excluded. While Settings → Privacy → "Don't save browsing history" (`history.saving_disabled`) is on, history doesn't sync: its switch is off and greyed out, and a sync under way when it is turned on applies no history.

`python3 tools/check_firefox_sync.py` exercises the built library against the local fake server. `./oganesson.py test firefox_sync` exercises the browser path. These checks must pass on the extracted build. They are not evidence of a real Mozilla-account test.

Before using this build with personal data, verify sign-in and two-way additions, edits, deletions, restart, and sign-out with a dedicated Mozilla test account and Firefox/Fenix. The original source documented no completed real-account verification and used an example application's OAuth client ID. Review that client identity before distribution. Use a fresh browser profile for validation.
