// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Privacy page's switches that stop saving browsing history and
// download history, and, while browsing history isn't saved, the one that
// still keeps closed tabs in memory to reopen.

import '../controls/settings_toggle_button.js';
import '../settings_shared.css.js';

import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

const SettingsHistorySavingElementBase = I18nMixin(PrefServiceObserverMixin(PolymerElement));

export class SettingsHistorySavingElement extends
    SettingsHistorySavingElementBase {
  static get is() {
    return 'settings-history-saving';
  }

  static get template() {
    return html`
      <style include="settings-shared"></style>
      <settings-toggle-button id="browsingHistory" class="hr"
          pref-key="history.saving_disabled"
          label="[[i18n('historySavingDisabled')]]"
          sub-label="[[i18n('historySavingDisabledDescription')]]">
      </settings-toggle-button>
      <settings-toggle-button id="keepClosedTabs" class="hr"
          hidden="[[!savingDisabledPref_.value]]"
          pref-key="oganesson.history.keep_closed_tabs"
          label="[[i18n('keepClosedTabs')]]"
          sub-label="[[i18n('keepClosedTabsDescription')]]">
      </settings-toggle-button>
      <settings-toggle-button id="downloadHistory" class="hr"
          pref-key="oganesson.downloads.saving_disabled"
          label="[[i18n('downloadHistorySavingDisabled')]]"
          sub-label="[[i18n('downloadHistorySavingDisabledDescription')]]">
      </settings-toggle-button>`;
  }

  static get properties() {
    return {
      savingDisabledPref_: Object,
    };
  }

  declare private savingDisabledPref_: chrome.settingsPrivate.PrefObject<boolean>|undefined;

  override connectedCallback() {
    super.connectedCallback();
    this.mirrorPref('history.saving_disabled', 'savingDisabledPref_');
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-history-saving': SettingsHistorySavingElement;
  }
}

customElements.define(
    SettingsHistorySavingElement.is, SettingsHistorySavingElement);
