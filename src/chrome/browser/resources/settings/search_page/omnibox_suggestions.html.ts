// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

import {html} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import type {SettingsOmniboxSuggestionsElement} from './omnibox_suggestions.js';

export function getHtml(this: SettingsOmniboxSuggestionsElement) {
  return html`<!--_html_template_start_-->
<div class="cr-row first">
  <div class="flex cr-padded-text">
    <h2>${this.i18n('omniboxSuggestions')}</h2>
    <div class="secondary">
      ${this.i18n('omniboxSuggestionsDescription')}
    </div>
  </div>
</div>
${this.historyNotSaved_ ? html`
<settings-toggle-button id="history" class="hr" disabled
    .pref="${this.offPref_}"
    label="${this.i18n('omniboxSuggestHistory')}"
    sub-label="${this.i18n('omniboxHistoryNotSaved')}">
</settings-toggle-button>` : html`
<settings-toggle-button id="history" class="hr"
    pref-key="oganesson.omnibox.suggest_history"
    label="${this.i18n('omniboxSuggestHistory')}">
</settings-toggle-button>`}
<settings-toggle-button id="bookmarks" class="hr"
    pref-key="oganesson.omnibox.suggest_bookmarks"
    label="${this.i18n('omniboxSuggestBookmarks')}">
</settings-toggle-button>
<settings-toggle-button id="openTabs" class="hr"
    pref-key="oganesson.omnibox.suggest_open_tabs"
    label="${this.i18n('omniboxSuggestOpenTabs')}"
    sub-label="${this.i18n('omniboxSuggestOpenTabsDescription')}">
</settings-toggle-button>
${this.historyNotSaved_ ? html`
<settings-toggle-button id="pastSearches" class="hr" disabled
    .pref="${this.offPref_}"
    label="${this.i18n('omniboxSuggestPastSearches')}"
    sub-label="${this.i18n('omniboxHistoryNotSaved')}">
</settings-toggle-button>` : html`
<settings-toggle-button id="pastSearches" class="hr"
    pref-key="oganesson.omnibox.suggest_past_searches"
    label="${this.i18n('omniboxSuggestPastSearches')}"
    sub-label="${this.i18n('omniboxSuggestPastSearchesDescription')}">
</settings-toggle-button>`}
<settings-toggle-button id="searchSuggestToggle" class="hr"
    pref-key="search.suggest_enabled"
    label="${this.i18n('searchSuggestPref')}"
    sub-label="${this.i18n('searchSuggestPrefDesc')}">
</settings-toggle-button>
<settings-toggle-button id="searchSuggestionsFirst" class="hr"
    pref-key="oganesson.omnibox.search_suggestions_first"
    label="${this.i18n('omniboxSearchSuggestionsFirst')}"
    sub-label="${this.i18n('omniboxSearchSuggestionsFirstDescription')}">
</settings-toggle-button>
<!--_html_template_end_-->`;
}
