// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef CHROME_BROWSER_IMPORTER_PROFILE_DISCOVERY_H_
#define CHROME_BROWSER_IMPORTER_PROFILE_DISCOVERY_H_

#include <vector>

#include "components/user_data_importer/common/importer_data_types.h"

namespace base {
class FilePath;
}

// Finds browser profiles by their files, not from a list of browsers: a
// Chromium-family user data folder holds "Local State", a Firefox-family one
// "profiles.ini". The Chrome and Firefox importers read whatever such a
// profile has, its favicons included when it keeps them.
namespace importer {

// The profiles in `dir`, a folder the user picked: a user data or profile
// folder, or a folder up to three levels above one.
std::vector<user_data_importer::SourceProfile> FindProfilesInFolder(
    const base::FilePath& dir);

// Adds the profiles under the usual application data folders that `profiles`
// doesn't hold yet. Leaves out this browser's own.
void AddDiscoveredProfiles(
    std::vector<user_data_importer::SourceProfile>* profiles);

}  // namespace importer

#endif  // CHROME_BROWSER_IMPORTER_PROFILE_DISCOVERY_H_
