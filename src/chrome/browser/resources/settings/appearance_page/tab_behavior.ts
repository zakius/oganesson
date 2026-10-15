// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Settings > Behavior > Tab behavior (docs/tab-behavior.md): a dropdown that
// sets the knobs below it to the Chromium or the Firefox preset, and shows
// Custom when they match neither. The prefs are the only state: the preset
// shown is derived from them.

import 'chrome://resources/cr_elements/md_select.css.js';
import '../controls/settings_dropdown_menu.js';
import '../controls/settings_toggle_button.js';
import '../settings_shared.css.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import type {DropdownMenuOptionList} from '../controls/settings_dropdown_menu.js';
import {loadTimeData} from '../i18n_setup.js';

// The presets, as values of the knobs' prefs (oganesson_pref_names.h).
// oganesson.tabs.link_position: 0 Chromium's, 1 Firefox's, 2 at the end.
const PRESETS: Record<string, Record<string, boolean|number>> = {
  chromium: {
    'oganesson.tabs.link_position': 0,
    'helium.browser.new_tab_next_to_active': false,
    'oganesson.tabs.select_related_on_close': true,
    'oganesson.tabs.select_owner_on_close': true,
    'oganesson.tabs.select_mru_on_close': false,
  },
  firefox: {
    'oganesson.tabs.link_position': 1,
    'helium.browser.new_tab_next_to_active': false,
    'oganesson.tabs.select_related_on_close': false,
    'oganesson.tabs.select_owner_on_close': true,
    'oganesson.tabs.select_mru_on_close': false,
  },
};

const SettingsTabBehaviorElementBase =
    I18nMixin(PrefServiceObserverMixin(PolymerElement));

export class SettingsTabBehaviorElement extends SettingsTabBehaviorElementBase {
  static get is() {
    return 'settings-tab-behavior';
  }

  // The preset names are browser names, not translated.
  static get template() {
    return html`
      <style include="cr-shared-style settings-shared md-select">
        :host {
          display: block;
        }
      </style>
      <div class="cr-row first">
        <div class="flex cr-padded-text" aria-hidden="true">
          [[i18n('tabBehavior')]]
        </div>
        <select id="tabBehavior" class="md-select"
            aria-label$="[[i18n('tabBehavior')]]"
            value="[[preset_]]" on-change="onPresetChange_">
          <option value="chromium">Chromium</option>
          <option value="firefox">Firefox</option>
          <option value="custom" disabled>[[i18n('tabBehaviorCustom')]]</option>
        </select>
      </div>
      <div class="list-frame">
        <div class="cr-row first">
          <div class="flex cr-padded-text" aria-hidden="true">
            [[i18n('tabLinkPosition')]]
          </div>
          <settings-dropdown-menu id="linkPosition"
              pref-key="oganesson.tabs.link_position"
              label="[[i18n('tabLinkPosition')]]"
              menu-options="[[linkPositions_]]">
          </settings-dropdown-menu>
        </div>
        <settings-toggle-button class="hr" id="newTabNextToActive"
            pref-key="helium.browser.new_tab_next_to_active"
            label="[[i18n('openNewTabNextToActive')]]">
        </settings-toggle-button>
        <settings-toggle-button class="hr" id="selectRelatedOnClose"
            pref-key="oganesson.tabs.select_related_on_close"
            label="[[i18n('tabSelectRelatedOnClose')]]">
        </settings-toggle-button>
        <settings-toggle-button class="hr" id="selectOwnerOnClose"
            pref-key="oganesson.tabs.select_owner_on_close"
            label="[[i18n('tabSelectOwnerOnClose')]]">
        </settings-toggle-button>
        <settings-toggle-button class="hr" id="selectMruOnClose"
            pref-key="oganesson.tabs.select_mru_on_close"
            label="[[i18n('tabSelectMruOnClose')]]">
        </settings-toggle-button>
      </div>`;
  }

  static get properties() {
    return {
      // A key of PRESETS, or 'custom'.
      preset_: String,

      // oganesson.tabs.link_position's values, in order.
      linkPositions_: {
        type: Array,
        value: () => [
          loadTimeData.getStringF('tabLinkPositionAsIn', 'Chromium'),
          loadTimeData.getStringF('tabLinkPositionAsIn', 'Firefox'),
          loadTimeData.getString('tabLinkPositionAtEnd'),
        ].map((name, value) => ({name, value})),
      },
    };
  }

  declare private preset_: string;
  declare private linkPositions_: DropdownMenuOptionList;
  private knobs_: Record<string, boolean|number> = {};

  override connectedCallback() {
    super.connectedCallback();
    for (const key of Object.keys(PRESETS['firefox'])) {
      this.addPrefObserver<boolean|number>(key, pref => {
        this.knobs_[key] = pref.value;
        this.preset_ = this.matchingPreset_();
      });
    }
  }

  private matchingPreset_(): string {
    return Object.keys(PRESETS).find(preset => {
      return Object.entries(PRESETS[preset])
          .every(([knob, value]) => this.knobs_[knob] === value);
    }) ?? 'custom';
  }

  private onPresetChange_(e: Event) {
    const preset = PRESETS[(e.target as HTMLSelectElement).value];
    for (const [knob, value] of Object.entries(preset ?? {})) {
      PrefService.getInstance().setPrefValue(knob, value);
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-tab-behavior': SettingsTabBehaviorElement;
  }
}

customElements.define(
    SettingsTabBehaviorElement.is, SettingsTabBehaviorElement);
