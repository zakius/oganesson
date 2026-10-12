// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#ifndef COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_
#define COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_

#include "components/omnibox/browser/autocomplete_match.h"

class AutocompleteInput;
class AutocompleteProvider;
class AutocompleteProviderClient;
class AutocompleteResult;
class PrefRegistrySimple;
class PrefService;

// The address bar's "Address bar suggestions" switches and suggestion order,
// on the Manage search engines settings page. AutocompleteController applies
// them to every provider's matches, so a source that's off doesn't come back
// through the shortcuts provider (the user's past selections) either.
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
// The order of the suggestion groups, a list of "bookmarks", "history",
// "open_tabs" and "searches". The rows below the first come in that order,
// and the first row autofills a site from bookmarks or history in it.
inline constexpr char kSuggestionOrder[] =
    "oganesson.omnibox.suggestion_order";

void RegisterSuggestionSourcePrefs(PrefRegistrySimple* registry);

// Whether a source's switch is on; true where the pref isn't registered.
// Browsing history and past searches, which come from history, are off while
// history isn't saved, whatever their switches say.
bool SuggestsFrom(const PrefService* prefs, const char* pref);

// `provider`'s matches without those from sources that are off. A past
// search for just what the user typed stays, as the search for it:
// SearchProvider merges its verbatim match into such a past search.
// BookmarkProvider's get the bookmarks it misses, matched as Firefox does. A
// bookmark or history page whose site starts with what the user typed adds
// an autofill match, which becomes the default match (see docs/omnibox.md).
ACMatches SuggestedMatches(AutocompleteProviderClient& client,
                           const AutocompleteInput& input,
                           AutocompleteProvider& provider);

// Puts the rows below the default match in kSuggestionOrder's groups,
// keeping Chromium's order within each. The default match stays.
void OrderSuggestions(const AutocompleteProviderClient& client,
                      const AutocompleteInput& input,
                      AutocompleteResult& result);

}  // namespace omnibox

#endif  // COMPONENTS_OMNIBOX_BROWSER_SUGGESTION_SOURCES_H_
