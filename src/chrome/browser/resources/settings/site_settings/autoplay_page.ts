// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Site settings → Autoplay: Firefox's three choices and the sites that are
// exceptions. The browser side is chrome/browser/content_settings/
// autoplay_setting.h.

import './category_setting_exceptions.js';
import './settings_category_default_radio_group.js';
import './site_settings_shared.css.js';
import '../settings_page/settings_subpage.js';
import '../settings_shared.css.js';

import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {SettingsViewMixin} from '../settings_page/settings_view_mixin.js';

import {ContentSettingsTypes} from './constants.js';

const AutoplayPageElementBase = SettingsViewMixin(I18nMixin(PolymerElement));

export class AutoplayPageElement extends AutoplayPageElementBase {
  static get is() {
    return 'settings-autoplay-page';
  }

  static get template() {
    return html`
      <style include="settings-shared site-settings-shared"></style>
      <settings-subpage page-title="[[i18n('siteSettingsAutoplay')]]"
          search-label="[[i18n('siteSettingsAllSitesSearch')]]"
          search-term="{{searchTerm}}" route-path$="[[routePath]]">
        <div class="content-settings-header secondary">
          [[i18n('siteSettingsAutoplayDescription')]]
        </div>
        <settings-category-default-radio-group category="[[category_]]"
            allow-option-label="[[i18n('siteSettingsAutoplayAllow')]]"
            allow-option-icon="cr:videocam"
            ask-option-label="[[i18n('siteSettingsAutoplayBlockAudio')]]"
            ask-option-sub-label="[[i18n('siteSettingsAutoplayBlockAudioSubLabel')]]"
            ask-option-icon="privacy:volume-off"
            block-option-label="[[i18n('siteSettingsAutoplayBlock')]]"
            block-option-sub-label="[[i18n('siteSettingsAutoplayBlockSubLabel')]]"
            block-option-icon="privacy:videocam-off">
        </settings-category-default-radio-group>
        <category-setting-exceptions category="[[category_]]"
            allow-header="[[i18n('siteSettingsAutoplayAllowedExceptions')]]"
            block-header="[[i18n('siteSettingsAutoplayBlockedExceptions')]]"
            search-filter="[[searchTerm]]">
        </category-setting-exceptions>
      </settings-subpage>`;
  }

  static get properties() {
    return {
      searchTerm: String,
      category_: {
        type: String,
        value: ContentSettingsTypes.AUTOPLAY,
      },
    };
  }

  declare searchTerm: string;
  declare private category_: ContentSettingsTypes;

  // SettingsViewMixin implementation.
  override focusBackButton() {
    this.shadowRoot!.querySelector('settings-subpage')!.focusBackButton();
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-autoplay-page': AutoplayPageElement;
  }
}

customElements.define(AutoplayPageElement.is, AutoplayPageElement);
