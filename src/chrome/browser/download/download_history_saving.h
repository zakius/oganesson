// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_DOWNLOAD_DOWNLOAD_HISTORY_SAVING_H_
#define CHROME_BROWSER_DOWNLOAD_DOWNLOAD_HISTORY_SAVING_H_

namespace prefs {

// While true, DownloadHistory saves no new downloads: they're listed only
// until the browser closes. The download counterpart of
// history.saving_disabled, which leaves downloads alone.
inline constexpr char kSavingDownloadHistoryDisabled[] =
    "oganesson.downloads.saving_disabled";

}  // namespace prefs

#endif  // CHROME_BROWSER_DOWNLOAD_DOWNLOAD_HISTORY_SAVING_H_
