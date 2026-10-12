// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_
#define COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_

#include "components/omnibox/browser/autocomplete_match.h"

class AutocompleteInput;
class AutocompleteResult;
class PrefRegistrySimple;
class PrefService;

// The address bar's "Address bar suggestions" switches, on the Manage search
// engines settings page. AutocompleteController applies them to every
// provider's matches, so a source that's off doesn't come back through the
// shortcuts provider (the user's past selections) either.
namespace omnibox {

// Pages from browsing history, including history shortcuts and the most
// visited pages offered on focus.
inline constexpr char kSuggestHistory[] = "oganesson.omnibox.suggest_history";
inline constexpr char kSuggestBookmarks[] =
    "oganesson.omnibox.suggest_bookmarks";
// "Switch to this tab" on a match, and the @tabs matches.
inline constexpr char kSuggestOpenTabs[] =
    "oganesson.omnibox.suggest_open_tabs";
// Searches the user made before, also offered on focus. Off by default.
inline constexpr char kSuggestPastSearches[] =
    "oganesson.omnibox.suggest_past_searches";
// Off by default: below the default match, history and bookmark pages rank
// above search rows. On, Chromium's order (searches first) applies.
inline constexpr char kSearchSuggestionsFirst[] =
    "oganesson.omnibox.search_suggestions_first";

void RegisterSuggestionSourcePrefs(PrefRegistrySimple* registry);

// Whether a source's switch is on; true where the pref isn't registered.
bool SuggestsFrom(const PrefService* prefs, const char* pref);

// `matches` without those from sources that are off. A past search for just
// what the user typed stays, as the search for it: SearchProvider merges its
// verbatim match into such a past search.
ACMatches SuggestedMatches(const PrefService* prefs,
                           const ACMatches& matches);

// Unless kSearchSuggestionsFirst is on, moves the search rows below the
// default match under the pages, keeping each kind's order. The default
// match stays: SortAndCull picks it as Chromium does.
void RankPagesAboveSearches(const PrefService* prefs,
                            const AutocompleteInput& input,
                            AutocompleteResult& result);

}  // namespace omnibox

#endif  // COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_
