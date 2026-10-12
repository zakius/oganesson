// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Manage search engines page's "Address bar suggestions" switches: which
// sources the address bar suggests from, and whether searches rank above
// pages. components/omnibox/browser/suggestion_sources.h applies them.

import '../controls/settings_toggle_button.js';

import {I18nMixinLit} from 'chrome://resources/cr_elements/i18n_mixin_lit.js';
import {CrLitElement} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss as getSettingsSharedCss} from '../settings_shared_lit.css.js';

import {getHtml} from './omnibox_suggestions.html.js';

const SettingsOmniboxSuggestionsElementBase = I18nMixinLit(CrLitElement);

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
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-omnibox-suggestions': SettingsOmniboxSuggestionsElement;
  }
}

customElements.define(
    SettingsOmniboxSuggestionsElement.is, SettingsOmniboxSuggestionsElement);
