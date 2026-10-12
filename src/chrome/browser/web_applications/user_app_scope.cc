// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/web_applications/user_app_scope.h"

#include <vector>

#include "base/strings/strcat.h"
#include "base/strings/string_split.h"
#include "base/strings/string_util.h"
#include "base/values.h"
#include "components/prefs/pref_service.h"
#include "components/prefs/scoped_user_pref_update.h"
#include "components/url_pattern/simple_url_pattern_matcher.h"
#include "components/url_pattern/url_pattern_util.h"
#include "third_party/liburlpattern/constructor_string_parser.h"
#include "third_party/liburlpattern/parse.h"
#include "third_party/liburlpattern/pattern.h"
#include "url/gurl.h"

namespace web_app {

namespace {

constexpr char kExclude[] = "!";

// Whether `pattern` names `host` itself, with no wildcard: such a rule narrows
// the app's scope on that host (#346). "https://*/login/*" names no host, so
// it doesn't narrow every site the app reaches. The pattern's host is compared
// canonicalized, as the matcher does: "bücher.de" names "xn--bcher-kva.de",
// "[\:\:1]" names "[::1]".
bool NamesHost(std::string_view pattern, std::string_view host) {
  liburlpattern::ConstructorStringParser parser(pattern);
  if (!parser
           .Parse([](std::string_view) -> base::expected<bool, absl::Status> {
             return true;
           })
           .ok()) {
    return false;
  }
  const std::optional<std::string_view>& hostname =
      parser.GetResult().hostname;
  if (!hostname) {
    return false;
  }
  auto parsed = liburlpattern::Parse(
      *hostname,
      url_pattern::TreatAsIPv6Hostname(*hostname)
          ? url_pattern::IPv6HostnameEncodeCallback
          : url_pattern::HostnameEncodeCallback,
      {.delimiter_list = ".", .prefix_list = ""});
  if (!parsed.has_value()) {
    return false;
  }
  std::string fixed;
  for (const liburlpattern::Part& part : parsed->PartList()) {
    if (part.type != liburlpattern::PartType::kFixed ||
        part.modifier != liburlpattern::Modifier::kNone) {
      return false;
    }
    fixed += part.value;
  }
  return fixed == host;
}

}  // namespace

bool IsUrlInUserAppScope(const PrefService& prefs,
                         const webapps::AppId& app_id,
                         const GURL& url,
                         bool in_manifest_scope) {
  const base::ListValue* rules =
      prefs.GetDict(kUserAppScopeRules).FindList(app_id);
  if (!rules) {
    return in_manifest_scope;
  }
  // A URL is in scope if an include rule matches it, or if the manifest's
  // scope has it and no include rule names its host; an exclusion wins.
  bool matched = false;
  bool host_named = false;
  // ponytail: compiles the rules on every check, which runs per navigation;
  // cache the matchers per app if that ever shows in a profile.
  for (const base::Value& rule : *rules) {
    if (!rule.is_string()) {
      continue;
    }
    std::string_view pattern = rule.GetString();
    bool exclude = pattern.starts_with(kExclude);
    if (exclude) {
      pattern.remove_prefix(1);
    }
    auto matcher =
        url_pattern::SimpleUrlPatternMatcher::Create(pattern, nullptr);
    if (!matcher.has_value()) {
      continue;
    }
    bool match = (*matcher)->Match(url);
    if (exclude) {
      if (match) {
        return false;
      }
      continue;
    }
    matched |= match;
    host_named |= NamesHost(pattern, url.host());
  }
  return matched || (in_manifest_scope && !host_named);
}

bool IsUrlExcludedFromUserAppScope(const PrefService& prefs,
                                   const webapps::AppId& app_id,
                                   const GURL& url) {
  const base::ListValue* rules =
      prefs.GetDict(kUserAppScopeRules).FindList(app_id);
  if (!rules) {
    return false;
  }
  for (const base::Value& rule : *rules) {
    if (!rule.is_string() || !rule.GetString().starts_with(kExclude)) {
      continue;
    }
    auto matcher = url_pattern::SimpleUrlPatternMatcher::Create(
        std::string_view(rule.GetString()).substr(1), nullptr);
    if (matcher.has_value() && (*matcher)->Match(url)) {
      return true;
    }
  }
  return false;
}

std::string GetUserAppScopeRules(const PrefService& prefs,
                                 const webapps::AppId& app_id) {
  std::vector<std::string_view> lines;
  if (const base::ListValue* rules =
          prefs.GetDict(kUserAppScopeRules).FindList(app_id)) {
    for (const base::Value& rule : *rules) {
      if (rule.is_string()) {
        lines.push_back(rule.GetString());
      }
    }
  }
  return base::JoinString(lines, "\n");
}

std::string SetUserAppScopeRules(PrefService& prefs,
                                 const webapps::AppId& app_id,
                                 std::string_view rules) {
  base::ListValue list;
  for (std::string_view line : base::SplitStringPiece(
           rules, "\n", base::TRIM_WHITESPACE, base::SPLIT_WANT_NONEMPTY)) {
    std::string_view pattern = line;
    if (pattern.starts_with(kExclude)) {
      pattern.remove_prefix(1);
    }
    auto matcher =
        url_pattern::SimpleUrlPatternMatcher::Create(pattern, nullptr);
    if (!matcher.has_value()) {
      return base::StrCat({"Invalid pattern \"", line, "\": ", matcher.error()});
    }
    list.Append(line);
  }
  ScopedDictPrefUpdate update(&prefs, kUserAppScopeRules);
  if (list.empty()) {
    update->Remove(app_id);
  } else {
    update->Set(app_id, std::move(list));
  }
  return std::string();
}

}  // namespace web_app
