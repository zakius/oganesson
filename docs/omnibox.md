# Address bar suggestions

Settings → Search engine → Manage search engines has an "Address bar suggestions" section. Its switches choose what the address bar suggests as you type, as Firefox's address bar settings do. Each switch is a profile pref:

| Switch | Pref | Default | What it covers |
|---|---|---|---|
| Browsing history | `oganesson.omnibox.suggest_history` | on | Pages you visited, history shortcuts (pages you opened from the address bar before), and the most visited pages offered on focus. |
| Bookmarks | `oganesson.omnibox.suggest_bookmarks` | on | Bookmarks, also when you opened one from the address bar before. |
| Open tabs | `oganesson.omnibox.suggest_open_tabs` | on | "Switch to this tab" on a suggestion that is open in another tab, and the `@tabs` results. |
| Past searches | `oganesson.omnibox.suggest_past_searches` | off | Searches you made before (the rows with a clock icon): from your history, from searches you picked in the address bar before, and on focus. |
| Improve search suggestions | `search.suggest_enabled` | Helium's | The search engine's own suggestions. The switch moved here from the Search engine page. |
| Search suggestions ahead of history and bookmarks | `oganesson.omnibox.search_suggestions_first` | off | The order of the rows below the first one. |

A switch that is off removes all matches of its source, whichever provider made them. A visited page that is also bookmarked still comes up as history while Browsing history is on.

When Past searches is off and you type exactly the words of a past search, the address bar still offers to search for them, as a plain search.

With Browsing history off, a URL you type still opens that URL, visited or not.

While Settings → Privacy and security has "Don't save browsing history" on, Browsing history and Past searches are off, whatever their switches say: past searches come from the history too, and history saved before stays in the profile. The two switches show off and greyed out, with a note naming that setting. Their prefs keep their values, so the switches come back as they were when history is saved again.

## Order

The first row is the one Enter opens. It is chosen as in Chromium: the best match that may be the default, which for a page means it completes what you typed inline (a site you often type), and otherwise the search for what you typed. The switches don't change it, except that a source that is off can't provide it. So Enter on a URL still opens it, and Enter on words that match no site still searches.

Below the first row, Chromium puts searches above pages. With "Search suggestions ahead of history and bookmarks" off, history and bookmark pages come first, then the searches: the search for what you typed, search suggestions and past searches. Each kind keeps its own order. This is Firefox's `browser.urlbar.showSearchSuggestionsFirst` set to false.

The on-focus suggestions (the address bar empty) keep Chromium's order.

## Code

`src/components/omnibox/browser/suggestion_sources.cc` has the prefs and both rules. `AutocompleteController` calls it at 2 points (`patches/oganesson/core/omnibox-suggestion-sources.patch`):

- `AggregateNewMatches()` passes each provider's matches through `SuggestedMatches()`, before sorting and deduplication, so a dropped match can't hide a match of the same page from a source that is on. With Open tabs off, it also marks every match as having no open tab, so `ConvertOpenTabMatches()` adds no "Switch to this tab".
- After the last `SortAndCull()`, `RankPagesAboveSearches()` sorts the rows below the default match.

A match's source comes from its type (`HISTORY_*`, `BOOKMARK_TITLE`, `SEARCH_HISTORY`, `OPEN_TAB`) and, for the shortcuts and most visited providers, from its provider. Shortcuts store a search as `SEARCH_HISTORY` and a page as `HISTORY_URL`, so a past search or page can't come back through them.

`HistoryURLProvider` returns early with Browsing history off, keeping only its what-you-typed match. Its history passes would otherwise replace that match with a history match the filter drops, and Enter on a URL would search.

The settings section is `src/chrome/browser/resources/settings/search_page/omnibox_suggestions.ts` (`patches/oganesson/settings/omnibox-suggestions-settings.patch`).

`tools/e2e/test_omnibox_suggestions.py` types into the address bar and reads its matches from chrome://omnibox. The on-focus past searches (Chromium's local history zero-suggest) only run with Google as the default search engine, so the test doesn't cover them.
