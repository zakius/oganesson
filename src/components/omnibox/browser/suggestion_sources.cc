// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "components/omnibox/browser/suggestion_sources.h"

#include <algorithm>
#include <array>
#include <iterator>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/i18n/case_conversion.h"
#include "base/strings/string_split.h"
#include "base/strings/string_util.h"
#include "base/strings/utf_string_conversions.h"
#include "base/values.h"
#include "components/bookmarks/browser/bookmark_model.h"
#include "components/bookmarks/browser/bookmark_node.h"
#include "components/omnibox/browser/autocomplete_input.h"
#include "components/omnibox/browser/autocomplete_match_classification.h"
#include "components/omnibox/browser/autocomplete_match_type.h"
#include "components/omnibox/browser/autocomplete_provider.h"
#include "components/omnibox/browser/autocomplete_provider_client.h"
#include "components/omnibox/browser/autocomplete_result.h"
#include "components/omnibox/browser/tab_matcher.h"
#include "components/prefs/pref_registry_simple.h"
#include "components/prefs/pref_service.h"
#include "components/search_engines/template_url.h"
#include "components/search_engines/template_url_service.h"
#include "components/url_formatter/url_formatter.h"
#include "ui/base/models/tree_node_iterator.h"
#include "url/gurl.h"

namespace omnibox {

namespace {

using Type = AutocompleteMatchType;

// The switch that covers `match`, or nullptr for matches no switch covers
// (what the user typed, search suggestions, keywords, chrome:// pages).
const char* SourceOf(const AutocompleteMatch& match) {
  switch (match.type) {
    case Type::kSearchHistory:
    case Type::kSearchSuggestPersonalized:
    case Type::kTileRepeatableQuery:
      return kSuggestPastSearches;
    case Type::kBookmarkTitle:
      return kSuggestBookmarks;
    case Type::kHistoryUrl:
    case Type::kHistoryTitle:
    case Type::kHistoryBody:
    case Type::kHistoryKeyword:
    case Type::kHistoryCluster:
    case Type::kHistoryEmbeddings:
    case Type::kHistoryEmbeddingsAnswer:
      return kSuggestHistory;
    case Type::kOpenTab:
    case Type::kTabGroup:
      return kSuggestOpenTabs;
    default:
      break;
  }
  if (!match.provider) {
    return nullptr;
  }
  switch (match.provider->type()) {
    // Shortcuts store searches as kSearchHistory, except
    // kSearchOtherEngine, and pages as kHistoryUrl.
    case AutocompleteProvider::Type::kShortcuts:
      return AutocompleteMatch::IsSearchType(match.type) ? kSuggestPastSearches
                                                         : kSuggestHistory;
    case AutocompleteProvider::Type::kMostVisitedSites:
      return kSuggestHistory;
    default:
      return nullptr;
  }
}

std::u16string Normalized(const std::u16string& text) {
  return base::i18n::ToLower(base::CollapseWhitespace(text, false));
}

// A search for exactly what the user typed.
bool SearchesTypedText(const AutocompleteMatch& match) {
  const auto& args = match.search_terms_args;
  return args && !args->original_query.empty() &&
         Normalized(args->search_terms) == Normalized(args->original_query);
}

// The groups of kSuggestionOrder, by their names in the pref.
enum Group { kBookmarks, kHistory, kOpenTabs, kSearches, kGroupCount };
constexpr std::array<std::string_view, kGroupCount> kGroupNames = {
    "bookmarks", "history", "open_tabs", "searches"};

// Replaced by kSuggestionOrder: "searches" first. Still registered, so that
// MigrateSearchSuggestionsFirst() can read a profile's old value.
constexpr char kSearchSuggestionsFirst[] =
    "oganesson.omnibox.search_suggestions_first";

base::ListValue DefaultOrder() {
  base::ListValue order;
  for (const auto name : kGroupNames) {
    order.Append(name);
  }
  return order;
}

// Each group's place in kSuggestionOrder. Groups the pref lacks follow in
// their default order, and names it doesn't know don't count.
std::array<int, kGroupCount> GroupRanks(const PrefService* prefs) {
  std::array<int, kGroupCount> ranks;
  ranks.fill(-1);
  int next = 0;
  auto place = [&](std::string_view name) {
    const auto it = std::ranges::find(kGroupNames, name);
    if (it != kGroupNames.end() && ranks[it - kGroupNames.begin()] < 0) {
      ranks[it - kGroupNames.begin()] = next++;
    }
  };
  if (prefs && prefs->FindPreference(kSuggestionOrder)) {
    for (const auto& name : prefs->GetList(kSuggestionOrder)) {
      if (name.is_string()) {
        place(name.GetString());
      }
    }
  }
  for (const auto name : kGroupNames) {
    place(name);
  }
  return ranks;
}

// A profile that had "Search suggestions ahead of history and bookmarks" on
// gets "searches" first, unless its order was changed since.
void MigrateSearchSuggestionsFirst(PrefService* prefs) {
  if (!prefs || !prefs->FindPreference(kSearchSuggestionsFirst) ||
      !prefs->HasPrefPath(kSearchSuggestionsFirst)) {
    return;
  }
  if (prefs->GetBoolean(kSearchSuggestionsFirst) &&
      prefs->FindPreference(kSuggestionOrder)->IsDefaultValue()) {
    base::ListValue order;
    order.Append(kGroupNames[kSearches]);
    for (const auto name : kGroupNames) {
      if (name != kGroupNames[kSearches]) {
        order.Append(name);
      }
    }
    prefs->SetList(kSuggestionOrder, std::move(order));
  }
  prefs->ClearPref(kSearchSuggestionsFirst);
}

// `url` as the user would type it: its host without "www.", port, path and
// query.
std::u16string SiteText(const GURL& url) {
  std::u16string site = base::UTF8ToUTF16(url.host());
  if (site.starts_with(u"www.")) {
    site.erase(0, 4);
  }
  if (url.has_port()) {
    site += u":" + base::UTF8ToUTF16(url.port());
  }
  return site;
}

// `text` without a leading http(s) scheme, which goes to `scheme`, and
// "www.".
std::u16string WithoutSchemeAndWww(std::u16string text, std::string& scheme) {
  for (std::string_view prefix : {"http://", "https://"}) {
    if (base::StartsWith(text, base::ASCIIToUTF16(prefix),
                         base::CompareCase::INSENSITIVE_ASCII)) {
      scheme = prefix.substr(0, prefix.size() - 3);
      text.erase(0, prefix.size());
    }
  }
  if (base::StartsWith(text, u"www.", base::CompareCase::INSENSITIVE_ASCII)) {
    text.erase(0, 4);
  }
  return text;
}

bool StartsWord(std::u16string_view text, size_t at) {
  return at == 0 || base::IsAsciiWhitespace(text[at - 1]) ||
         base::IsAsciiPunctuation(text[at - 1]);
}

// How well a bookmark matches the typed words, as Firefox matches them: 0
// when its site starts with what was typed, 1 when each word starts a word
// of its title or address, 2 when each is anywhere in them; nullopt when a
// word is in neither.
std::optional<int> BookmarkTier(const std::vector<std::u16string>& words,
                                const std::u16string& title,
                                const std::u16string& address) {
  int tier = 1;
  for (const auto& word : words) {
    bool starts = false, found = false;
    for (const auto* text : {&title, &address}) {
      for (size_t at = text->find(word); at != std::u16string::npos;
           at = text->find(word, at + 1)) {
        found = true;
        starts = starts || StartsWord(*text, at);
      }
    }
    if (!found) {
      return std::nullopt;
    }
    tier = starts ? tier : 2;
  }
  return words.size() == 1 && address.starts_with(words[0]) ? 0 : tier;
}

// BookmarkProvider's matches, plus the bookmarks it misses: its index only
// matches word starts, and it keeps 3. Every bookmark whose title or
// address has each typed word anywhere counts, up to the dropdown's size.
// With Bookmarks first in the order, they all rank by BookmarkTier(), then
// the most recently used, above the other rows (the default match aside),
// so that the dropdown shows them all; otherwise BookmarkProvider's keep
// Chromium's scores and the others come below them.
// ponytail: scans every bookmark per update; an index if that gets slow.
ACMatches BookmarkMatches(AutocompleteProviderClient& client,
                          const AutocompleteInput& input,
                          AutocompleteProvider& provider,
                          bool bookmarks_first) {
  ACMatches matches = provider.matches();
  const bookmarks::BookmarkModel* model = client.GetBookmarkModel();
  if (!model || !model->loaded() || input.IsZeroSuggest() ||
      input.in_keyword_mode()) {
    return matches;
  }
  std::string scheme;
  const std::u16string typed =
      base::i18n::ToLower(WithoutSchemeAndWww(input.text(), scheme));
  std::vector<std::u16string> words;
  for (const auto& word : base::SplitString(
           typed, base::kWhitespaceUTF16, base::TRIM_WHITESPACE,
           base::SPLIT_WANT_NONEMPTY)) {
    words.push_back(word);
  }
  if (words.empty()) {
    return matches;
  }
  struct Found {
    int tier;
    const bookmarks::BookmarkNode* node;
  };
  std::map<GURL, Found> by_url;
  ui::TreeNodeIterator<const bookmarks::BookmarkNode> it(model->root_node());
  while (it.has_next()) {
    const bookmarks::BookmarkNode* node = it.Next();
    if (!node->is_url() ||
        (!scheme.empty() && node->url().scheme() != scheme)) {
      continue;
    }
    const auto tier = BookmarkTier(
        words, base::i18n::ToLower(node->GetTitle()),
        base::i18n::ToLower(SiteText(node->url()) +
                            base::UTF8ToUTF16(node->url().PathForRequest())));
    if (!tier) {
      continue;
    }
    auto [entry, added] = by_url.try_emplace(node->url(), Found{*tier, node});
    if (!added &&
        node->date_last_used() > entry->second.node->date_last_used()) {
      entry->second.node = node;
    }
  }
  std::vector<std::pair<GURL, Found>> found(by_url.begin(), by_url.end());
  std::ranges::stable_sort(found, [](const auto& a, const auto& b) {
    if (a.second.tier != b.second.tier) {
      return a.second.tier < b.second.tier;
    }
    if (a.second.node->date_last_used() != b.second.node->date_last_used()) {
      return a.second.node->date_last_used() > b.second.node->date_last_used();
    }
    return a.second.node->date_added() > b.second.node->date_added();
  });
  std::map<GURL, int> place;
  for (const auto& [url, entry] : found) {
    place.try_emplace(url, place.size());
  }
  const int count = found.size();
  if (bookmarks_first) {
    for (size_t i = 0; i < matches.size(); ++i) {
      const auto at = place.find(matches[i].destination_url);
      matches[i].relevance =
          1499 - std::min(at == place.end() ? count + int(i) : at->second, 199);
      matches[i].allowed_to_be_default_match = false;
    }
  }
  std::set<GURL> listed;
  for (const auto& match : matches) {
    listed.insert(match.destination_url);
  }
  const size_t limit = AutocompleteResult::GetMaxMatches();
  for (const auto& [url, entry] : found) {
    if (place[url] >= int(limit)) {
      break;
    }
    if (listed.contains(url)) {
      continue;
    }
    AutocompleteMatch match(&provider,
                            (bookmarks_first ? 1499 : 899) - place[url], false,
                            Type::kBookmarkTitle);
    match.destination_url = url;
    const std::u16string shown = url_formatter::FormatUrl(
        url, AutocompleteMatch::GetFormatTypes(!scheme.empty(), false),
        base::UnescapeRule::SPACES, nullptr, nullptr, nullptr);
    match.contents = shown;
    match.contents_class = ClassifyTermMatches(
        FindTermMatches(typed, shown, true, true), shown.size(),
        ACMatchClassification::MATCH | ACMatchClassification::URL,
        ACMatchClassification::URL);
    match.description = entry.node->GetTitle();
    match.description_class = ClassifyTermMatches(
        FindTermMatches(typed, match.description, true, true),
        match.description.size(), ACMatchClassification::MATCH,
        ACMatchClassification::NONE);
    match.fill_into_edit =
        AutocompleteInput::FormattedStringWithEquivalentMeaning(
            url,
            url_formatter::FormatUrl(url, url_formatter::kFormatUrlOmitDefaults,
                                     base::UnescapeRule::SPACES, nullptr,
                                     nullptr, nullptr),
            client.GetSchemeClassifier(), nullptr);
    match.RecordAdditionalInfo("oganesson bookmark tier", entry.tier);
    matches.push_back(std::move(match));
  }
  return matches;
}

// The additional info that marks an autofill match.
constexpr char kAutofill[] = "oganesson autofill";

// Firefox's autofill. When what the user typed starts the site of `match`, a
// bookmark or history page, the match for that site's root, completing the
// site inline; when it goes on into the page's path, the match for the
// page. Hosts are compared without "www.", and a typed scheme must be the
// page's.
std::optional<AutocompleteMatch> AutofillMatch(const AutocompleteMatch& match,
                                               const AutocompleteInput& input,
                                               std::u16string_view typed,
                                               std::string_view scheme,
                                               int rank) {
  const GURL& url = match.destination_url;
  if (!url.SchemeIsHTTPOrHTTPS() || (!scheme.empty() && url.scheme() != scheme)) {
    return std::nullopt;
  }
  const std::u16string site = SiteText(url);
  const std::u16string root = site + u"/";
  const std::u16string page = site + base::UTF8ToUTF16(url.PathForRequest());
  GURL destination;
  std::u16string rest;
  if (base::StartsWith(root, typed, base::CompareCase::INSENSITIVE_ASCII)) {
    destination = url.GetWithEmptyPath();
    rest = root.substr(typed.size());
    // "twit" completes to "twitter.com", as Chromium shows a site.
    if (!rest.empty()) {
      rest.pop_back();
    }
  } else if (base::StartsWith(page, typed,
                              base::CompareCase::INSENSITIVE_ASCII)) {
    destination = url.GetWithoutRef();
    rest = page.substr(typed.size());
  } else {
    return std::nullopt;
  }
  // The group's rank first, then the shortest completion.
  const int relevance =
      1600 - 100 * rank - std::min<int>(typed.size() + rest.size(), 99);
  AutocompleteMatch autofill(match.provider, relevance, false, match.type);
  autofill.destination_url = destination;
  autofill.fill_into_edit = input.text() + rest;
  autofill.inline_autocompletion = rest;
  autofill.contents = autofill.fill_into_edit;
  autofill.contents_class.emplace_back(
      0, ACMatchClassification::URL | ACMatchClassification::MATCH);
  if (!rest.empty()) {
    autofill.contents_class.emplace_back(input.text().size(),
                                         ACMatchClassification::URL);
  }
  // The title is the page's, not the site's.
  if (destination == url) {
    autofill.description = match.description;
    autofill.description_class = match.description_class;
  }
  autofill.SetAllowedToBeDefault(input);
  autofill.RecordAdditionalInfo(kAutofill,
                                destination == url ? "page" : "site");
  return autofill;
}

// What the user typed, for autofill: without its http(s) scheme, which goes
// to `scheme`, and "www.". Empty where Firefox doesn't autofill: on focus,
// after the user deleted text, with a space, a forced search, or a search
// keyword.
std::u16string AutofillText(const AutocompleteProviderClient& client,
                            const AutocompleteInput& input,
                            std::string& scheme) {
  const std::u16string& text = input.text();
  if (input.IsZeroSuggest() || input.prevent_inline_autocomplete() ||
      input.in_keyword_mode() ||
      input.type() == ::metrics::OmniboxInputType::QUERY ||
      std::ranges::any_of(text, base::IsUnicodeWhitespace<char16_t>)) {
    return {};
  }
  const TemplateURLService* engines = client.GetTemplateURLService();
  if (engines && engines->GetTemplateURLForKeyword(base::i18n::ToLower(text))) {
    return {};
  }
  return WithoutSchemeAndWww(text, scheme);
}

// Where a row below the default match goes: rows above the groups (featured
// site searches, starter pack), each group in kSuggestionOrder, then rows no
// group covers, among them the what-you-typed URL, then Chromium's bottom
// rows.
int SortKey(const AutocompleteMatch& match,
            const AutocompleteProviderClient& client,
            const AutocompleteInput& input,
            const std::array<int, kGroupCount>& ranks,
            bool tabs) {
  const int order = match.GetSortingOrder();
  if (order < 2) {
    return order;
  }
  if (order > 4) {
    return 100 + order;
  }
  const char* source = SourceOf(match);
  Group group = kGroupCount;
  if (match.type == Type::kUrlWhatYouTyped) {
    group = kGroupCount;
  } else if (tabs && (source == kSuggestOpenTabs ||
                      (!AutocompleteMatch::IsSearchType(match.type) &&
                       client.GetTabMatcher().IsTabOpenWithURL(
                           match.destination_url, &input)))) {
    group = kOpenTabs;
  } else if (source == kSuggestBookmarks) {
    group = kBookmarks;
  } else if (source == kSuggestHistory) {
    group = kHistory;
  } else if (source == kSuggestPastSearches ||
             AutocompleteMatch::IsSearchType(match.type) ||
             match.type == Type::kNavsuggest ||
             match.type == Type::kNavsuggestPersonalized) {
    group = kSearches;
  }
  return 10 + (group == kGroupCount ? kGroupCount : ranks[group]);
}

}  // namespace

void RegisterSuggestionSourcePrefs(PrefRegistrySimple* registry) {
  registry->RegisterBooleanPref(kSuggestHistory, true);
  registry->RegisterBooleanPref(kSuggestBookmarks, true);
  registry->RegisterBooleanPref(kSuggestOpenTabs, true);
  registry->RegisterBooleanPref(kSuggestPastSearches, false);
  registry->RegisterListPref(kSuggestionOrder, DefaultOrder());
  registry->RegisterBooleanPref(kSearchSuggestionsFirst, false);
}

bool SuggestsFrom(const PrefService* prefs, const char* pref) {
  if (!prefs || !prefs->FindPreference(pref)) {
    return true;
  }
  // prefs::kSavingBrowserHistoryDisabled, which this target can't include.
  static constexpr char kSavingBrowserHistoryDisabled[] =
      "history.saving_disabled";
  if ((std::string_view(pref) == kSuggestHistory ||
       std::string_view(pref) == kSuggestPastSearches) &&
      prefs->FindPreference(kSavingBrowserHistoryDisabled) &&
      prefs->GetBoolean(kSavingBrowserHistoryDisabled)) {
    return false;
  }
  return prefs->GetBoolean(pref);
}

ACMatches SuggestedMatches(AutocompleteProviderClient& client,
                           const AutocompleteInput& input,
                           AutocompleteProvider& provider) {
  const PrefService* prefs = client.GetPrefs();
  ACMatches kept;
  const bool tabs = SuggestsFrom(prefs, kSuggestOpenTabs);
  std::string scheme;
  const std::u16string typed = AutofillText(client, input, scheme);
  const auto ranks = GroupRanks(prefs);
  const ACMatches matches =
      provider.type() == AutocompleteProvider::Type::kBookmark &&
              SuggestsFrom(prefs, kSuggestBookmarks)
          ? BookmarkMatches(client, input, provider, ranks[kBookmarks] == 0)
          : provider.matches();
  ACMatches autofills;
  for (const auto& match : matches) {
    const char* source = SourceOf(match);
    if (source && !SuggestsFrom(prefs, source)) {
      if (source != kSuggestPastSearches || !SearchesTypedText(match)) {
        continue;
      }
      kept.push_back(match);
      // The search icon, not the past search clock.
      kept.back().type = Type::kSearchWhatYouTyped;
    } else {
      kept.push_back(match);
      if (!typed.empty() &&
          (source == kSuggestBookmarks || source == kSuggestHistory)) {
        auto autofill = AutofillMatch(
            match, input, typed, scheme,
            ranks[source == kSuggestBookmarks ? kBookmarks : kHistory]);
        if (autofill) {
          autofills.push_back(std::move(*autofill));
        }
      }
    }
    // AutocompleteResult::ConvertOpenTabMatches() leaves a match alone once
    // this has a value.
    if (!tabs) {
      kept.back().has_tab_match = false;
    }
  }
  // The best one; OrderSuggestions() drops another provider's that loses.
  const auto best = std::ranges::max_element(autofills, {},
                                             &AutocompleteMatch::relevance);
  if (best != autofills.end()) {
    if (!tabs) {
      best->has_tab_match = false;
    }
    kept.push_back(std::move(*best));
  }
  return kept;
}

void OrderSuggestions(const AutocompleteProviderClient& client,
                      const AutocompleteInput& input,
                      AutocompleteResult& result) {
  MigrateSearchSuggestionsFirst(client.GetPrefs());
  if (input.IsZeroSuggest() || result.size() < 3) {
    return;
  }
  const auto ranks = GroupRanks(client.GetPrefs());
  const bool tabs = SuggestsFrom(client.GetPrefs(), kSuggestOpenTabs);
  // Rows in suggestion groups come last, under their group's header.
  auto begin = std::next(result.begin());
  auto end = std::find_if(begin, result.end(), [](const auto& match) {
    return match.suggestion_group_id.has_value();
  });
  std::vector<std::pair<int, AutocompleteMatch>> rows;
  bool losing_autofill = false;
  for (auto it = begin; it != end; ++it) {
    rows.emplace_back(SortKey(*it, client, input, ranks, tabs),
                      std::move(*it));
    losing_autofill |=
        !rows.back().second.GetAdditionalInfoForDebugging(kAutofill).empty();
  }
  std::ranges::stable_sort(rows, {}, &std::pair<int, AutocompleteMatch>::first);
  for (auto& row : rows) {
    *begin++ = std::move(row.second);
  }
  if (!losing_autofill) {
    return;
  }
  // Only the default match autofills: another one, from another provider
  // than the winner's, goes. AutocompleteResult can't erase a match, so the
  // matches go back in without it.
  ACMatches kept;
  for (auto it = result.begin(); it != result.end(); ++it) {
    if (it == result.begin() ||
        it->GetAdditionalInfoForDebugging(kAutofill).empty()) {
      kept.push_back(std::move(*it));
    }
  }
  const auto groups = result.suggestion_groups_map();
  const std::string hint = result.smart_compose_inline_hint();
  result.ClearMatches();
  result.AppendMatches(kept);
  result.MergeSuggestionGroupsMap(groups);
  result.set_smart_compose_inline_hint(hint);
}

}  // namespace omnibox
