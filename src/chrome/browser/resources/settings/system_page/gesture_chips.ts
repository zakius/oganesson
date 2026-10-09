// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

import 'chrome://resources/cr_elements/cr_icon_button/cr_icon_button.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '../settings_shared.css.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {loadTimeData} from '../i18n_setup.js';

import type {GestureValue} from './mouse_gestures.js';
import {CHIP_STYLE, getGestureLabel, GESTURES_PREF, gesturesFor, mouseGesturesEnabled} from './mouse_gestures.js';

const GestureChipsElementBase = I18nMixin(PrefServiceObserverMixin(PolymerElement));

// The gesture chips of one command, each with a remove button.
export class SettingsGestureChipsElement extends GestureChipsElementBase {
  static get is() {
    return 'settings-gesture-chips';
  }

  static get template() {
    return html`${CHIP_STYLE}
      <template is="dom-repeat" items="[[getChains_(value, gestures_)]]"
          as="chain">
        <span class="shortcut-chip" title$="[[i18n('shortcutsGestureLabel')]]">
          <span class="shortcut-label">[[getLabel_(chain)]]</span>
          <cr-icon-button class="icon-clear" title$="[[i18n('remove')]]"
              data-chain$="[[chain]]"
              aria-label$="[[getRemoveLabel_(name, chain)]]"
              on-click="onRemoveClick_">
          </cr-icon-button>
        </span>
      </template>`;
  }

  static get properties() {
    return {
      value: Object,
      name: String,
      gestures_: {
        type: Object,
        value: () => ({}),
      },
    };
  }

  declare value: GestureValue|null;
  declare name: string;
  declare private gestures_: Record<string, GestureValue>;

  override connectedCallback() {
    super.connectedCallback();
    this.addPrefObserver<Record<string, GestureValue>>(
        GESTURES_PREF, pref => this.gestures_ = pref.value);
  }

  private getChains_(
      value: GestureValue|null,
      gestures: Record<string, GestureValue>): string[] {
    return mouseGesturesEnabled() ? gesturesFor(value, gestures) : [];
  }

  private getLabel_(chain: string): string {
    return getGestureLabel(chain);
  }

  private getRemoveLabel_(name: string, chain: string): string {
    return loadTimeData.getStringF(
        'shortcutsRemoveA11yLabel', getGestureLabel(chain), name);
  }

  private onRemoveClick_(e: Event) {
    const chain = (e.currentTarget as HTMLElement).dataset['chain'];
    if (chain) {
      PrefService.getInstance().deletePrefDictEntry(GESTURES_PREF, chain);
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-gesture-chips': SettingsGestureChipsElement;
  }
}

customElements.define(SettingsGestureChipsElement.is, SettingsGestureChipsElement);
