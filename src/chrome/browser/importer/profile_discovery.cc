// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/importer/profile_discovery.h"

#include <algorithm>
#include <set>
#include <string>
#include <string_view>
#include <utility>

#include "base/base_paths.h"
#include "base/files/file_enumerator.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/path_service.h"
#include "base/strings/utf_string_conversions.h"
#include "base/threading/scoped_blocking_call.h"
#include "build/build_config.h"
#include "chrome/common/chrome_paths.h"
#include "chrome/common/importer/chrome_importer_utils.h"
#include "chrome/common/importer/firefox_importer_utils.h"
#include "chrome/common/ini_parser.h"
#include "chrome/grit/generated_resources.h"
#include "sql/database.h"
#include "sql/statement.h"
#include "ui/base/l10n/l10n_util.h"

#if BUILDFLAG(IS_LINUX)
#include "base/environment.h"
#include "base/nix/xdg_util.h"
#endif

namespace importer {

namespace {

using user_data_importer::SourceProfile;

// Folder names that don't name the browser, as in ".../Chrome/User Data" or
// "~/snap/firefox/common/.mozilla/firefox".
constexpr std::string_view kGenericFolderNames[] = {
    "User Data", "config", "common", "current", "data", "Profiles"};

std::u16string FolderName(base::FilePath dir) {
  for (; dir != dir.DirName(); dir = dir.DirName()) {
    std::string name = dir.BaseName().AsUTF8Unsafe();
    if (name.starts_with('.')) {
      name.erase(0, 1);
    }
    if (!name.empty() && !std::ranges::contains(kGenericFolderNames, name)) {
      return base::UTF8ToUTF16(name);
    }
  }
  return dir.AsUTF16Unsafe();
}

// Profiles from the browsers ImporterList knows come first and keep their
// names; these name the rest by kind and folder. The engine names are
// arguments because the build renames Chromium in every UI string.
std::u16string ChromiumName(const base::FilePath& dir) {
  return l10n_util::GetStringFUTF16(IDS_OGANESSON_IMPORT_BASED_ON, u"Chromium",
                                    FolderName(dir));
}

std::u16string FirefoxName(const base::FilePath& dir) {
  return l10n_util::GetStringFUTF16(IDS_OGANESSON_IMPORT_BASED_ON, u"Firefox",
                                    FolderName(dir));
}

void AddChromiumProfile(const base::FilePath& dir,
                        const std::u16string& browser,
                        const std::u16string& name,
                        std::vector<SourceProfile>* profiles) {
  uint16_t items;
  if (!ChromeImporterCanImport(dir, user_data_importer::TYPE_CHROME, &items)) {
    return;
  }
  SourceProfile profile;
  profile.importer_name = browser;
  profile.importer_type = user_data_importer::TYPE_CHROME;
  profile.services_supported = items;
  profile.source_path = dir;
  profile.profile = name;
  profiles->push_back(std::move(profile));
}

void AddFirefoxProfile(const base::FilePath& dir,
                       std::u16string browser,
                       const std::u16string& name,
                       std::vector<SourceProfile>* profiles) {
  // Thunderbird profiles have places.sqlite too, and always a Mail folder.
  if (!base::PathExists(dir.AppendASCII("places.sqlite")) ||
      base::DirectoryExists(dir.AppendASCII("Mail"))) {
    return;
  }
  int version = 0;
  base::FilePath app_path;
  GetFirefoxVersionAndPathFromProfile(dir, &version, &app_path);
  if (base::PathExists(app_path.AppendASCII("application.ini"))) {
    browser = GetFirefoxImporterName(app_path);
  }
  SourceProfile profile;
  profile.importer_name = std::move(browser);
  profile.importer_type = user_data_importer::TYPE_FIREFOX;
  profile.services_supported =
      user_data_importer::HISTORY | user_data_importer::FAVORITES;
  profile.source_path = dir;
  profile.app_path = app_path;
  profile.profile = name;
  profiles->push_back(std::move(profile));
}

// Adds the profiles `dir` holds. False when it isn't a user data or profile
// folder, so its subfolders may be.
bool AddProfilesIn(const base::FilePath& dir,
                   std::vector<SourceProfile>* profiles) {
  if (base::PathExists(dir.AppendASCII("Local State"))) {
    const std::u16string browser = ChromiumName(dir);
    for (const base::Value& entry :
         GetChromeSourceProfiles(dir.AppendASCII("Local State"))) {
      const base::DictValue& dict = entry.GetDict();
      AddChromiumProfile(
          dir.Append(base::FilePath::FromUTF8Unsafe(*dict.FindString("id"))),
          browser, base::UTF8ToUTF16(*dict.FindString("name")), profiles);
    }
    return true;
  }
  const base::FilePath ini_file = dir.AppendASCII("profiles.ini");
  if (base::PathExists(ini_file)) {
    std::string content;
    base::ReadFileToString(ini_file, &content);
    DictionaryValueINIParser ini;
    ini.Parse(content);
    const std::u16string browser = FirefoxName(dir);
    for (const FirefoxDetail& detail :
         GetFirefoxDetailsFromDictionary(ini.root(), std::string(), dir)) {
      AddFirefoxProfile(detail.path, browser, detail.name, profiles);
    }
    return true;
  }
  if (base::PathExists(dir.AppendASCII("places.sqlite"))) {
    AddFirefoxProfile(dir, FirefoxName(dir.DirName()),
                      dir.BaseName().AsUTF16Unsafe(), profiles);
    return true;
  }
  if (base::PathExists(dir.AppendASCII("Preferences"))) {
    AddChromiumProfile(dir, ChromiumName(dir.DirName()),
                       dir.BaseName().AsUTF16Unsafe(), profiles);
    return true;
  }
  return false;
}

// ponytail: a depth-limited walk; it stats a few files in every folder it
// visits, so the roots and depths stay small.
void Walk(const base::FilePath& dir,
          int depth,
          const base::FilePath& own_user_data,
          std::vector<SourceProfile>* profiles) {
  if (dir == own_user_data || AddProfilesIn(dir, profiles) || depth == 0) {
    return;
  }
  base::FileEnumerator subfolders(dir, false,
                                  base::FileEnumerator::DIRECTORIES);
  for (base::FilePath subfolder = subfolders.Next(); !subfolder.empty();
       subfolder = subfolders.Next()) {
    Walk(subfolder, depth - 1, own_user_data, profiles);
  }
}

// Whether a Firefox profile holds something to import: a visit, or a
// bookmark added after Firefox's default set (a minute after the places root).
// Each Firefox install makes its own profile, and the first run a legacy one,
// which hold only the default bookmarks. A profile Firefox holds locked counts.
bool HasUserData(const base::FilePath& dir) {
  sql::Database db(sql::DatabaseOptions().set_read_only(true),
                   "FirefoxImporter");
  if (!db.Open(dir.AppendASCII("places.sqlite"))) {
    return true;
  }
  sql::Statement found(db.GetUniqueStatement(
      "SELECT 1 FROM moz_historyvisits UNION ALL "
      "SELECT 1 FROM moz_bookmarks WHERE type = 1 AND dateAdded > "
      "(SELECT MIN(dateAdded) FROM moz_bookmarks) + 60000000 LIMIT 1"));
  return found.Step() || !found.Succeeded();
}

base::FilePath OwnUserData() {
  base::FilePath dir;
  base::PathService::Get(chrome::DIR_USER_DATA, &dir);
  return dir;
}

}  // namespace

std::vector<SourceProfile> FindProfilesInFolder(const base::FilePath& dir) {
  base::ScopedBlockingCall blocking(FROM_HERE, base::BlockingType::MAY_BLOCK);
  std::vector<SourceProfile> profiles;
  Walk(dir, 3, OwnUserData(), &profiles);
  return profiles;
}

void AddDiscoveredProfiles(std::vector<SourceProfile>* profiles) {
  base::ScopedBlockingCall blocking(FROM_HERE, base::BlockingType::MAY_BLOCK);
  // Folder and how deep below it a user data folder may be.
  std::vector<std::pair<base::FilePath, int>> roots;
  base::FilePath home;
  base::PathService::Get(base::DIR_HOME, &home);
#if BUILDFLAG(IS_LINUX)
  auto env = base::Environment::Create();
  // ~/.config/vivaldi, ~/.config/BraveSoftware/Brave-Browser,
  // ~/.config/mozilla/firefox.
  roots.emplace_back(base::nix::GetXDGDirectory(env.get(),
                                                base::nix::kXdgConfigHomeEnvVar,
                                                base::nix::kDotConfigDir),
                     2);
  // ~/.var/app/org.mozilla.firefox/config/mozilla/firefox,
  // ~/snap/firefox/common/.mozilla/firefox.
  roots.emplace_back(home.Append(".var/app"), 4);
  roots.emplace_back(home.Append("snap"), 4);
  // ~/.mozilla/firefox, ~/.librewolf.
  base::FileEnumerator dot_folders(home, false,
                                   base::FileEnumerator::DIRECTORIES, ".*");
  for (base::FilePath dir = dot_folders.Next(); !dir.empty();
       dir = dot_folders.Next()) {
    if (dir.BaseName().value() != ".config" &&
        dir.BaseName().value() != ".var") {
      roots.emplace_back(dir, 1);
    }
  }
#elif BUILDFLAG(IS_WIN)
  // %LOCALAPPDATA%\Google\Chrome\User Data, %APPDATA%\Mozilla\Firefox.
  base::FilePath dir;
  if (base::PathService::Get(base::DIR_LOCAL_APP_DATA, &dir)) {
    roots.emplace_back(dir, 3);
  }
  if (base::PathService::Get(base::DIR_ROAMING_APP_DATA, &dir)) {
    roots.emplace_back(dir, 3);
  }
#elif BUILDFLAG(IS_MAC)
  // ~/Library/Application Support/Google/Chrome.
  base::FilePath dir;
  if (base::PathService::Get(base::DIR_APP_DATA, &dir)) {
    roots.emplace_back(dir, 3);
  }
#endif
  const base::FilePath own_user_data = OwnUserData();
  std::vector<SourceProfile> found;
  for (const auto& [root, depth] : roots) {
    Walk(root, depth, own_user_data, &found);
  }
  for (SourceProfile& profile : found) {
    const bool known =
        std::ranges::any_of(*profiles, [&](const SourceProfile& p) {
          return p.source_path == profile.source_path;
        });
    if (!known) {
      profiles->push_back(std::move(profile));
    }
  }
  std::erase_if(*profiles, [](const SourceProfile& profile) {
    return profile.importer_type == user_data_importer::TYPE_FIREFOX &&
           !HasUserData(profile.source_path);
  });
  // Entries that would still read the same get their folder's name.
  std::set<std::pair<std::u16string, std::u16string>> seen, clashing;
  for (const SourceProfile& profile : *profiles) {
    if (!seen.emplace(profile.importer_name, profile.profile).second) {
      clashing.emplace(profile.importer_name, profile.profile);
    }
  }
  for (SourceProfile& profile : *profiles) {
    if (clashing.contains({profile.importer_name, profile.profile})) {
      const std::u16string folder =
          profile.source_path.BaseName().AsUTF16Unsafe();
      profile.profile = profile.profile.empty()
                            ? folder
                            : profile.profile + u" (" + folder + u")";
    }
  }
}

}  // namespace importer
