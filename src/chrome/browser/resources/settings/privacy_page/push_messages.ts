// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Browser traffic's push messages: the opt-in switch and the push server
// (oganesson/core/push-opt-in.patch). Helium's autopush driver reads both
// from Helium's prefs; an empty server means Mozilla's.

import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import '../controls/settings_toggle_button.js';
import '../settings_shared.css.js';

import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import type {CrInputElement} from 'chrome://resources/cr_elements/cr_input/cr_input.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

const ENABLED_PREF = 'helium.services.web_push';
const SERVER_PREF = 'helium.services.push_server';

// What helium::GetPushServiceURL accepts: empty for Mozilla's, wss, or ws on
// localhost (net::IsLocalhost).
function isPushServer(value: string): boolean {
  if (!value) {
    return true;
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  const host = url.hostname;
  const localhost = host === 'localhost' || host.endsWith('.localhost') ||
      host === '[::1]' || /^127\.\d+\.\d+\.\d+$/.test(host);
  return url.protocol === 'wss:' || (url.protocol === 'ws:' && localhost);
}

const SettingsPushMessagesElementBase =
    I18nMixin(PrefServiceObserverMixin(PolymerElement));

export class SettingsPushMessagesElement extends
    SettingsPushMessagesElementBase {
  static get is() {
    return 'settings-push-messages';
  }

  static get template() {
    return html`
      <style include="settings-shared">
        #serverRow cr-input {
          flex: 1;
        }
      </style>
      <settings-toggle-button id="pushMessages" class="hr"
          pref-key="helium.services.web_push"
          label="[[i18n('browserTrafficPush')]]"
          sub-label="[[i18n('browserTrafficPushDescription')]]">
      </settings-toggle-button>
      <div id="serverRow" class="cr-row continuation"
          hidden="[[!enabledPref_.value]]">
        <cr-input id="pushServer" value="[[serverPref_.value]]"
            label="[[i18n('browserTrafficPushServer')]]"
            placeholder="wss://push.services.mozilla.com/"
            invalid="[[invalid_]]"
            error-message="[[i18n('browserTrafficPushServerInvalid')]]"
            spellcheck="false" on-change="onServerChange_"
            on-input="onServerInput_">
        </cr-input>
      </div>
      <div class="cr-row continuation" hidden="[[!enabledPref_.value]]">
        <div class="cr-padded-text secondary">
          [[i18n('browserTrafficPushServerDescription')]]
        </div>
      </div>`;
  }

  static get properties() {
    return {
      enabledPref_: Object,
      serverPref_: Object,
      invalid_: {
        type: Boolean,
        value: false,
      },
    };
  }

  declare private enabledPref_:
      chrome.settingsPrivate.PrefObject<boolean>|undefined;
  declare private serverPref_:
      chrome.settingsPrivate.PrefObject<string>|undefined;
  declare private invalid_: boolean;

  override connectedCallback() {
    super.connectedCallback();
    this.mirrorPref(ENABLED_PREF, 'enabledPref_');
    this.mirrorPref(SERVER_PREF, 'serverPref_');
  }

  private onServerInput_() {
    this.invalid_ = false;
  }

  // Only a server the browser accepts is saved.
  private onServerChange_(e: Event) {
    const value = (e.target as CrInputElement).value.trim();
    this.invalid_ = !isPushServer(value);
    if (!this.invalid_) {
      chrome.settingsPrivate.setPref(SERVER_PREF, value);
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-push-messages': SettingsPushMessagesElement;
  }
}

customElements.define(
    SettingsPushMessagesElement.is, SettingsPushMessagesElement);
