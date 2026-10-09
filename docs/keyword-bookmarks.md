# Keyword bookmarks

Firefox's bookmark keywords: a bookmark can have a keyword, and the address bar opens it when you type the keyword.

- **Setting a keyword.** The bookmark bubble (the star, or Ctrl+D) and the bookmark editor ("Edit…" on a bookmark, or "Choose another folder…" in the bubble) have a Keyword field. Keywords are lowercase and have no spaces. A keyword names one URL: every bookmark of the URL has it, and giving it to another URL takes it off the first. The bookmark manager (`chrome://bookmarks`) has no Keyword field.
- **Using it.** Typing `keyword terms` opens the bookmark's URL with `%s` replaced by the terms, escaped as a URL query value, and `%S` replaced by the terms as typed. Typing the keyword alone opens the URL with `%s` and `%S` removed. If the URL has neither, `keyword terms` stays an ordinary search. The match is the omnibox's default, above search suggestions.
- **Storage.** The keyword is the bookmark's meta info `oganesson.keyword`, in the profile's `Bookmarks` file.
- **Firefox Sync.** Bookmark records carry the keyword both ways. Firefox keeps one keyword per URL, so every bookmark of that URL gets it. See [`firefox-sync.md`](firefox-sync.md).

Code: `bookmarks::ResolveBookmarkKeyword` and friends in `components/bookmarks/browser/bookmark_utils.cc`; the omnibox match in `BookmarkProvider` (so Helium's `omnibox-autocomplete-filtering` flag without `bookmarks` turns keywords off too).

Verified by `./oganesson.py test bookmarks`: keyword with terms, keyword alone, after a restart, and the editor showing the keyword. The sync mapping is covered by the `bookmarks.rs` unit test (a keyword reaching the ops, and its removal); it hasn't run against a real account.
