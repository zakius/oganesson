// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "components/omnibox/browser/suggestion_sources.h"

#include <algorithm>
#include <iterator>

#include "base/i18n/case_conversion.h"
#include "base/strings/string_util.h"
#include "components/omnibox/browser/autocomplete_input.h"
#include "components/omnibox/browser/autocomplete_match_type.h"
#include "components/omnibox/browser/autocomplete_provider.h"
#include "components/omnibox/browser/autocomplete_result.h"
#include "components/prefs/pref_registry_simple.h"
#include "components/prefs/pref_service.h"
#include "components/search_engines/template_url.h"

namespace omnibox {

namespace {

using Type = AutocompleteMatchType;

// The switch that covers `match`, or nullptr for matches no switch covers
// (what the user typed, search suggestions, keywords, chrome:// pages).
const char* SourceOf(const AutocompleteMatch& match) {
  switch (match.type) {
    case Type::SEARCH_HISTORY:
    case Type::SEARCH_SUGGEST_PERSONALIZED:
    case Type::TILE_REPEATABLE_QUERY:
      return kSuggestPastSearches;
    case Type::BOOKMARK_TITLE:
      return kSuggestBookmarks;
    case Type::HISTORY_URL:
    case Type::HISTORY_TITLE:
    case Type::HISTORY_BODY:
    case Type::HISTORY_KEYWORD:
    case Type::HISTORY_CLUSTER:
    case Type::HISTORY_EMBEDDINGS:
    case Type::HISTORY_EMBEDDINGS_ANSWER:
      return kSuggestHistory;
    case Type::OPEN_TAB:
    case Type::TAB_GROUP:
      return kSuggestOpenTabs;
    default:
      break;
  }
  if (!match.provider) {
    return nullptr;
  }
  switch (match.provider->type()) {
    // Shortcuts store searches as SEARCH_HISTORY, except
    // SEARCH_OTHER_ENGINE, and pages as HISTORY_URL.
    case AutocompleteProvider::TYPE_SHORTCUTS:
      return AutocompleteMatch::IsSearchType(match.type) ? kSuggestPastSearches
                                                         : kSuggestHistory;
    case AutocompleteProvider::TYPE_MOST_VISITED_SITES:
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

// GetSortingOrder() puts searches (3) above pages (4); this swaps the two.
// Starter pack rows stay above both, and the bottom rows (8 and up) below.
int PagesFirstOrder(const AutocompleteMatch& match) {
  const int order = match.GetSortingOrder();
  if (order == 3 && AutocompleteMatch::IsSearchType(match.type)) {
    return 4;
  }
  return order == 4 ? 3 : order;
}

}  // namespace

void RegisterSuggestionSourcePrefs(PrefRegistrySimple* registry) {
  registry->RegisterBooleanPref(kSuggestHistory, true);
  registry->RegisterBooleanPref(kSuggestBookmarks, true);
  registry->RegisterBooleanPref(kSuggestOpenTabs, true);
  registry->RegisterBooleanPref(kSuggestPastSearches, false);
  registry->RegisterBooleanPref(kSearchSuggestionsFirst, false);
}

bool SuggestsFrom(const PrefService* prefs, const char* pref) {
  if (!prefs || !prefs->FindPreference(pref)) {
    return true;
  }
  return prefs->GetBoolean(pref);
}

ACMatches SuggestedMatches(const PrefService* prefs,
                           const ACMatches& matches) {
  ACMatches kept;
  const bool tabs = SuggestsFrom(prefs, kSuggestOpenTabs);
  for (const auto& match : matches) {
    const char* source = SourceOf(match);
    if (source && !SuggestsFrom(prefs, source)) {
      if (source != kSuggestPastSearches || !SearchesTypedText(match)) {
        continue;
      }
      kept.push_back(match);
      // The search icon, not the past search clock.
      kept.back().type = Type::SEARCH_WHAT_YOU_TYPED;
    } else {
      kept.push_back(match);
    }
    // AutocompleteResult::ConvertOpenTabMatches() leaves a match alone once
    // this has a value.
    if (!tabs) {
      kept.back().has_tab_match = false;
    }
  }
  return kept;
}

void RankPagesAboveSearches(const PrefService* prefs,
                            const AutocompleteInput& input,
                            AutocompleteResult& result) {
  if (input.IsZeroSuggest() || result.size() < 3 ||
      SuggestsFrom(prefs, kSearchSuggestionsFirst)) {
    return;
  }
  // Rows in suggestion groups come last, under their group's header.
  auto begin = std::next(result.begin());
  auto end = std::find_if(begin, result.end(), [](const auto& match) {
    return match.suggestion_group_id.has_value();
  });
  std::stable_sort(begin, end, [](const auto& a, const auto& b) {
    return PagesFirstOrder(a) < PagesFirstOrder(b);
  });
}

}  // namespace omnibox
