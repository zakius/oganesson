// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_FIREFOX_ABOUT_URLS_H_
#define CHROME_BROWSER_FIREFOX_ABOUT_URLS_H_

class GURL;

// Firefox's about: pages that have a Chromium counterpart, such as
// about:preferences, open it: this rewrites their chrome:// form (which
// url_formatter::FixupURL makes of about:foo) to the Chromium page.
void RewriteFirefoxAboutURL(GURL* url);

#endif  // CHROME_BROWSER_FIREFOX_ABOUT_URLS_H_
