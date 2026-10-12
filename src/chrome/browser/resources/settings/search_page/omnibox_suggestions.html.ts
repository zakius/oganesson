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
<div class="cr-row">
  <div class="flex cr-padded-text">
    <div id="orderLabel">${this.i18n('omniboxSuggestionOrder')}</div>
    <div class="secondary">${this.i18n('omniboxSuggestionOrderDescription')}</div>
  </div>
</div>
<div id="order" class="list-frame" role="list" aria-labelledby="orderLabel">
  ${this.order_.map((group, index) => html`
  <div class="list-item ${this.isOff_(group) ? 'off' : ''}" role="listitem"
      data-group="${group}">
    <div class="start label">
      <div>${this.label_(group)}</div>
      ${this.isOff_(group) ? html`
      <div class="secondary">${this.i18n('omniboxGroupOff')}</div>` : ''}
    </div>
    <cr-icon-button id="${group}-up" iron-icon="cr:keyboard-arrow-up"
        data-index="${index}" data-step="-1" ?disabled="${index === 0}"
        aria-label="${this.i18n('omniboxMoveUp', this.label_(group))}"
        title="${this.i18n('omniboxMoveUp', this.label_(group))}"
        @click="${this.onMoveClick_}">
    </cr-icon-button>
    <cr-icon-button id="${group}-down" iron-icon="cr:keyboard-arrow-down"
        data-index="${index}" data-step="1"
        ?disabled="${index === this.order_.length - 1}"
        aria-label="${this.i18n('omniboxMoveDown', this.label_(group))}"
        title="${this.i18n('omniboxMoveDown', this.label_(group))}"
        @click="${this.onMoveClick_}">
    </cr-icon-button>
  </div>`)}
</div>
<!--_html_template_end_-->`;
}
