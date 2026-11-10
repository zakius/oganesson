# Address bar suggestions

Settings → Search engine → Manage search engines has an "Address bar suggestions" section. Its switches choose what the address bar suggests as you type, as Firefox's address bar settings do, and its "Suggestion order" list orders the suggestions. Each switch is a profile pref:

| Switch | Pref | Default | What it covers |
|---|---|---|---|
| Browsing history | `oganesson.omnibox.suggest_history` | on | Pages you visited, history shortcuts (pages you opened from the address bar before), and the most visited pages offered on focus. |
| Bookmarks | `oganesson.omnibox.suggest_bookmarks` | on | Bookmarks, also when you opened one from the address bar before. |
| Open tabs | `oganesson.omnibox.suggest_open_tabs` | on | "Switch to this tab" on a suggestion that is open in another tab, and the `@tabs` results. |
| Past searches | `oganesson.omnibox.suggest_past_searches` | off | Searches you made before (the rows with a clock icon): from your history, from searches you picked in the address bar before, and on focus. |
| Improve search suggestions | `search.suggest_enabled` | Helium's | The search engine's own suggestions. The switch moved here from the Search engine page. |

A switch that is off removes all matches of its source, whichever provider made them. A visited page that is also bookmarked still comes up as history while Browsing history is on.

When Past searches is off and you type exactly the words of a past search, the address bar still offers to search for them, as a plain search.

With Browsing history off, a URL you type still opens that URL, visited or not.

While Settings → Privacy and security has "Don't save browsing history" on, Browsing history and Past searches are off, whatever their switches say: past searches come from the history too, and history saved before stays in the profile. The two switches show off and greyed out, with a note naming that setting. Their prefs keep their values, so the switches come back as they were when history is saved again.

## Order

"Suggestion order" lists 4 groups, each with up and down buttons: Bookmarks, Browsing history, Open tabs and Searches, in that default order. The pref is `oganesson.omnibox.suggestion_order`, a list of `bookmarks`, `history`, `open_tabs` and `searches`. A group whose switch is off keeps its place, greyed out and marked "Off".

The rows below the first come in the groups' order. Within a group, they keep Chromium's order.

- Bookmarks: bookmarks, also from the shortcuts provider.
- Browsing history: visited pages and history shortcuts.
- Open tabs: rows with "Switch to this tab", and the `@tabs` results. While Open tabs is off, a page that is open stays in its own group.
- Searches: the search for what you typed, search suggestions, past searches, and the sites the search engine suggests (navsuggest), which come with its suggestions.

The what-you-typed URL (the globe row: `twit` as `http://twit/`) comes after all groups. For a word, it is the least likely row. Where the input looks like a URL, it is usually the first row anyway, and so not in the groups.

Rows Chromium keeps outside its search and page order keep their places: featured site searches and the starter pack (`@bookmarks`) above the groups, its bottom rows below. The on-focus suggestions (the address bar empty) keep Chromium's order.

The old "Search suggestions ahead of history and bookmarks" switch (`oganesson.omnibox.search_suggestions_first`) is gone. A profile that had it on gets Searches first, unless its order was changed already, and the old pref is cleared. The address bar does this the first time it runs; the settings page shows the new order from then.

## Bookmark matching

Bookmarks match as in Firefox: each typed word anywhere in the title or the address (host without `www.`, path and query), ignoring case. `itter` finds "Twitter", and `news` finds a bookmark on `quillnews.example` whatever its title. Chromium's own bookmark index only matches the starts of words, and its provider keeps 3 bookmarks.

All matching bookmarks are offered, up to the dropdown's size (Chromium's 8 rows, at most 7 of them pages). With Bookmarks first in the order, they rank above the other rows below the first: bookmarks whose site starts with what you typed, then those where each word starts a word of the title or address, then the others, each by when you last opened them. With another group first, Chromium's bookmark matches keep their scores and the others come below them.

A bookmark can't be the first row this way; it gets there through autofill.

## The first row: autofill

The first row is the one Enter opens. As in Firefox, when what you typed starts the address of a site from your bookmarks or browsing history, the first row is that site, its address completed inline: `twit` gives `twit|ter.com`, and Enter opens `https://twitter.com/`, the site's root as Firefox's autofill does, whatever page of the site the bookmark or visit is. Typed further, into a path (`twitter.com/h`), the completion is a whole bookmarked or visited address (`twitter.com/home`).

- Hosts are compared without `www.`. A typed `http://` or `https://` must be the site's.
- Candidates come from the groups in the order: by default a bookmark wins over history. Within a group, the shortest completion wins.
- Bookmarks need their switch on. History needs its switch on and history saved.
- No autofill after a space, for a search keyword (a search engine's keyword, typed alone), in keyword mode, for a forced search (`?twit`), or while you delete text (Chromium's rule for inline completion).
- Without a candidate, the first row is chosen as in Chromium: the search for what you typed, a URL you typed, or a site Chromium completes from history. So Enter on a URL still opens it, and Enter on words that match no site still searches. With history on, Chromium's own inline completion of a typed site still applies; for the same site, the result is the same.

In the expanded address bar, the text field sits above the rows. When the first row is the search for what you typed, the field shows `twit` with the search engine's icon and the first row is `twit - Google Search`: that is one match, not a duplicate.

## Code

`src/components/omnibox/browser/suggestion_sources.cc` has the prefs, the filter, autofill and the order. `AutocompleteController` calls it at 2 points (`patches/oganesson/core/omnibox-suggestion-sources.patch`):

- `AggregateNewMatches()` passes each provider through `SuggestedMatches()`, which returns the provider's matches to keep, before sorting and deduplication, so a dropped match can't hide a match of the same page from a source that is on. With Open tabs off, it also marks every match as having no open tab, so `ConvertOpenTabMatches()` adds no "Switch to this tab".
  For each bookmark or history match it keeps, it adds the autofill match when one applies (see above). Its relevance (1600, less 100 per group above it, less the completion's length) puts it above Chromium's matches outside keyword mode, so `SortAndCull()` picks it as the default.
  For BookmarkProvider, it first adds the bookmarks the provider missed, from a pass over the bookmark model (see Bookmark matching). The hook passes it the provider, so it knows which one it is even when the provider has no matches.
- After the last `SortAndCull()`, `OrderSuggestions()` migrates the old "ahead" pref and sorts the rows below the default match into the groups.

A match's source comes from its type (`HISTORY_*`, `BOOKMARK_TITLE`, `SEARCH_HISTORY`, `OPEN_TAB`) and, for the shortcuts and most visited providers, from its provider. Shortcuts store a search as `SEARCH_HISTORY` and a page as `HISTORY_URL`, so a past search or page can't come back through them.

`HistoryURLProvider` returns early with Browsing history off, keeping only its what-you-typed match. Its history passes would otherwise replace that match with a history match the filter drops, and Enter on a URL would search.

The settings section is `src/chrome/browser/resources/settings/search_page/omnibox_suggestions.ts` (`patches/oganesson/settings/omnibox-suggestions-settings.patch`).

`tools/e2e/test_omnibox_suggestions.py` types into the address bar and reads its matches from chrome://omnibox. The on-focus past searches (Chromium's local history zero-suggest) only run with Google as the default search engine, so the test doesn't cover them.
