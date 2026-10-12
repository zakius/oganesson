// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Manage search engines page's "Address bar suggestions" switches: which
// sources the address bar suggests from, and whether searches rank above
// pages. components/omnibox/browser/suggestion_sources.h applies them.
// While browsing history isn't saved (history.saving_disabled), the two
// switches whose suggestions come from history show off and greyed out; their
// prefs keep the user's choice for when it is saved again.

import '../controls/settings_toggle_button.js';

import {PrefServiceObserverMixinLit} from '/shared/settings/prefs2/pref_service_observer_mixin_lit.js';
import {I18nMixinLit} from 'chrome://resources/cr_elements/i18n_mixin_lit.js';
import {CrLitElement} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss as getSettingsSharedCss} from '../settings_shared_lit.css.js';

import {getHtml} from './omnibox_suggestions.html.js';

const SettingsOmniboxSuggestionsElementBase =
    PrefServiceObserverMixinLit(I18nMixinLit(CrLitElement));

export class SettingsOmniboxSuggestionsElement extends
    SettingsOmniboxSuggestionsElementBase {
  static get is() {
    return 'settings-omnibox-suggestions';
  }

  static override get styles() {
    return getSettingsSharedCss();
  }

  override render() {
    return getHtml.bind(this)();
  }

  static override get properties() {
    return {
      historyNotSaved_: {type: Boolean},
      offPref_: {type: Object},
    };
  }

  protected accessor historyNotSaved_: boolean = false;

  // The pref a switch shows while history isn't saved: off, and never set.
  protected accessor offPref_: chrome.settingsPrivate.PrefObject<boolean> = {
    key: '',
    type: chrome.settingsPrivate.PrefType.BOOLEAN,
    value: false,
  };

  override connectedCallback() {
    super.connectedCallback();
    this.addPrefObserver<boolean>('history.saving_disabled', pref => {
      this.historyNotSaved_ = pref.value;
    });
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-omnibox-suggestions': SettingsOmniboxSuggestionsElement;
  }
}

customElements.define(
    SettingsOmniboxSuggestionsElement.is, SettingsOmniboxSuggestionsElement);
