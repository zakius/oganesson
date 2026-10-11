// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Firefox Sync section of the "Autofill and passwords" page: sign-in,
// servers, the synced types, and tabs from Firefox devices. Talks to
// FirefoxSyncHandler.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import '../settings_page/settings_section.js';
import '../settings_shared.css.js';

import type {CrInputElement} from 'chrome://resources/cr_elements/cr_input/cr_input.js';
import type {CrToggleElement} from 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {WebUiListenerMixin} from 'chrome://resources/cr_elements/web_ui_listener_mixin.js';
import {sendWithPromise} from 'chrome://resources/js/cr.js';
import type {DomRepeatEvent} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

/** From FirefoxSyncHandler (oganesson). */
interface FirefoxSyncType {
  name: string;
  label: string;
  supported: boolean;
  enabled: boolean;
  // Off because the browser doesn't save this data (history).
  blocked?: boolean;
  count?: number;
  error?: string;
}

interface FirefoxSyncStatus {
  available: boolean;
  signedIn?: boolean;
  email?: string;
  syncing?: boolean;
  lastSync?: number;
  count?: number;
  error?: string;
  needsSignIn?: boolean;
  server?: string;
  syncServer?: string;
  canSignIn?: boolean;
  types?: FirefoxSyncType[];
}

const SettingsFirefoxSyncElementBase = I18nMixin(WebUiListenerMixin(PolymerElement));

export class SettingsFirefoxSyncElement extends SettingsFirefoxSyncElementBase {
  static get is() {
    return 'settings-firefox-sync';
  }

  static get template() {
    return html`
      <style include="cr-shared-style settings-shared">
        #firefoxSync cr-button,
        #firefoxSyncServerRow cr-button {
          margin-inline-start: 8px;
        }
      </style>
      <settings-section page-title="[[i18n('firefoxSyncSectionTitle')]]"
          hidden="[[!firefoxSync_.available]]">
        <div id="firefoxSync" class="cr-row first">
          <div class="flex cr-padded-text">
            <div>[[firefoxSyncTitle_(firefoxSync_)]]</div>
            <div class="secondary">[[firefoxSyncDetail_(firefoxSync_)]]</div>
          </div>
          <cr-button class="action-button" on-click="onFirefoxSyncSignIn_"
              hidden="[[!showFirefoxSyncSignIn_(firefoxSync_)]]"
              disabled="[[!firefoxSync_.canSignIn]]">
            [[i18n('firefoxSyncSignIn')]]
          </cr-button>
          <cr-button on-click="onFirefoxSyncNow_"
              hidden="[[!firefoxSync_.signedIn]]"
              disabled="[[firefoxSync_.syncing]]">
            [[i18n('firefoxSyncSyncNow')]]
          </cr-button>
          <cr-button on-click="onFirefoxSyncSignOut_"
              hidden="[[!firefoxSync_.signedIn]]">
            [[i18n('firefoxSyncSignOut')]]
          </cr-button>
        </div>
        <div id="firefoxSyncServerRow" class="cr-row">
          <cr-input id="firefoxSyncServer" class="flex" label="[[i18n('firefoxSyncAccountServer')]]"
              placeholder="accounts.example.com" value="[[firefoxSyncServer_]]"
              on-change="onFirefoxSyncServerChange_">
          </cr-input>
          <cr-button on-click="onFirefoxSyncMozilla_">
            [[i18n('firefoxSyncUseMozilla')]]
          </cr-button>
        </div>
        <div class="cr-row">
          <cr-input id="firefoxSyncStorageServer" class="flex" label="[[i18n('firefoxSyncStorageServer')]]"
              placeholder="[[i18n('firefoxSyncStorageServerDefault')]]"
              value="[[firefoxSyncStorageServer_]]"
              on-change="onFirefoxSyncStorageServerChange_">
          </cr-input>
        </div>
        <template is="dom-repeat" items="[[firefoxSync_.types]]">
          <div class="cr-row">
            <div class="flex cr-padded-text">
              <div>[[item.label]]</div>
              <div class="secondary">[[firefoxSyncTypeDetail_(item)]]</div>
            </div>
            <cr-toggle checked="[[item.enabled]]" aria-label="[[item.label]]"
                disabled="[[!firefoxSyncTypeToggleable_(item, firefoxSync_)]]"
                on-change="onFirefoxSyncTypeChange_">
            </cr-toggle>
          </div>
        </template>
      </settings-section>`;
  }

  static get properties() {
    return {
      firefoxSync_: {
        type: Object,
        value: () => ({available: false}),
      },

      // The field's text, set only when the saved server changes, so status
      // updates during a sync keep what the user is typing.
      firefoxSyncServer_: String,
      firefoxSyncStorageServer_: String,
    };
  }

  declare private firefoxSync_: FirefoxSyncStatus;
  declare private firefoxSyncServer_: string;
  declare private firefoxSyncStorageServer_: string;

  override connectedCallback() {
    super.connectedCallback();
    const setFirefoxSync = (status: FirefoxSyncStatus) => {
      if (status.server !== this.firefoxSync_.server) {
        this.firefoxSyncServer_ = status.server || '';
      }
      if (status.syncServer !== this.firefoxSync_.syncServer) {
        this.firefoxSyncStorageServer_ = status.syncServer || '';
      }
      this.firefoxSync_ = status;
    };
    sendWithPromise<FirefoxSyncStatus>('getFirefoxSyncStatus')
        .then(setFirefoxSync);
    this.addWebUiListener('firefox-sync-status-changed', setFirefoxSync);
  }

  private firefoxSyncTitle_(status: FirefoxSyncStatus): string {
    return status.signedIn ?
        this.i18n('firefoxSyncSignedInAs', status.email || '') :
        this.i18n('firefoxSyncTitle');
  }

  private firefoxSyncDetail_(status: FirefoxSyncStatus): string {
    if (status.syncing) {
      return this.i18n('firefoxSyncSyncing');
    }
    if (status.error) {
      return status.error;
    }
    if (!status.signedIn && !status.canSignIn) {
      return this.i18n('firefoxSyncNeedsServer');
    }
    if (!status.signedIn) {
      return this.i18n('firefoxSyncSignInDescription');
    }
    if (!status.lastSync) {
      return this.i18n('firefoxSyncNotSynced');
    }
    return this.i18n(
        'firefoxSyncLastSynced', new Date(status.lastSync).toLocaleString());
  }

  private firefoxSyncTypeDetail_(type: FirefoxSyncType): string {
    if (!type.supported) {
      return this.i18n('firefoxSyncNotSupported');
    }
    if (type.blocked) {
      return this.i18n('firefoxSyncHistoryNotSaved');
    }
    if (type.error) {
      return type.error;
    }
    return type.count === undefined ?
        '' :
        this.i18n('firefoxSyncCount', type.count.toLocaleString());
  }

  private firefoxSyncTypeToggleable_(
      type: FirefoxSyncType, status: FirefoxSyncStatus): boolean {
    return type.supported && !type.blocked && !status.syncing;
  }

  private onFirefoxSyncTypeChange_(e: DomRepeatEvent<FirefoxSyncType>) {
    const toggle = e.target as CrToggleElement;
    chrome.send('setFirefoxSyncType', [e.model.item.name, toggle.checked]);
  }

  private showFirefoxSyncSignIn_(status: FirefoxSyncStatus): boolean {
    return !status.signedIn || !!status.needsSignIn;
  }

  private onFirefoxSyncSignIn_() {
    chrome.send('firefoxSyncSignIn');
  }

  private onFirefoxSyncServerChange_(e: Event) {
    chrome.send(
        'setFirefoxSyncServer', [(e.target as CrInputElement).value, false]);
  }

  private onFirefoxSyncStorageServerChange_(e: Event) {
    chrome.send(
        'setFirefoxSyncServer', [(e.target as CrInputElement).value, true]);
  }

  private onFirefoxSyncMozilla_() {
    chrome.send('setFirefoxSyncServer', ['', true]);
    chrome.send('setFirefoxSyncServer', ['https://accounts.firefox.com', false]);
  }

  private onFirefoxSyncNow_() {
    chrome.send('firefoxSyncNow');
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-firefox-sync': SettingsFirefoxSyncElement;
  }
}

customElements.define(SettingsFirefoxSyncElement.is, SettingsFirefoxSyncElement);
