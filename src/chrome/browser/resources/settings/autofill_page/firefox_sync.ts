// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Firefox Sync section, the people page's ("Sync") only one: the
// Mozilla account card, what syncs, the servers, and Import. Talks to
// FirefoxSyncHandler; the account's picture is the browser profile's, which
// FirefoxSyncService sets from the account.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_collapse/cr_collapse.js';
import 'chrome://resources/cr_elements/cr_expand_button/cr_expand_button.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/cr_link_row/cr_link_row.js';
import 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import '../settings_page/settings_section.js';
import '../settings_shared.css.js';

import type {CrInputElement} from 'chrome://resources/cr_elements/cr_input/cr_input.js';
import type {CrToggleElement} from 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {WebUiListenerMixin} from 'chrome://resources/cr_elements/web_ui_listener_mixin.js';
import {sendWithPromise} from 'chrome://resources/js/cr.js';
import {OpenWindowProxyImpl} from 'chrome://resources/js/open_window_proxy.js';
import type {DomRepeatEvent} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';
import type {ProfileInfo} from '/shared/settings/people_page/profile_info_browser_proxy.js';

import {routes} from '../route.js';
import {Router} from '../router.js';
import {ProfileInfoBrowserProxyImpl} from '/shared/settings/people_page/profile_info_browser_proxy.js';

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
  name?: string;
  syncing?: boolean;
  signingIn?: boolean;
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
        #avatar {
          border-radius: 50%;
          flex-shrink: 0;
          height: 40px;
          margin-inline-end: 16px;
          width: 40px;
        }
        #firefoxSync .name {
          font-weight: 500;
        }
        #firefoxSync .paused {
          color: var(--cr-fallback-color-error, var(--google-red-600));
        }
        cr-collapse .cr-row,
        cr-collapse cr-link-row {
          padding-inline-start: 40px;
        }
      </style>
      <settings-section page-title="[[i18n('firefoxSyncSectionTitle')]]"
          hidden="[[!firefoxSync_.available]]">
        <div id="firefoxSync" class="cr-row first">
          <img id="avatar" src="[[avatar_]]" alt=""
              hidden="[[!firefoxSync_.signedIn]]">
          <div class="flex cr-padded-text">
            <div class="name">[[firefoxSyncTitle_(firefoxSync_)]]</div>
            <div class$="secondary [[pausedClass_(firefoxSync_)]]"
                >[[firefoxSyncDetail_(firefoxSync_)]]</div>
            <div class="secondary" hidden="[[!showEmail_(firefoxSync_)]]"
                >[[firefoxSync_.email]]</div>
          </div>
          <cr-button class="action-button" on-click="onFirefoxSyncSignIn_"
              hidden="[[!showFirefoxSyncSignIn_(firefoxSync_)]]"
              disabled="[[!firefoxSync_.canSignIn]]">
            [[signInLabel_(firefoxSync_)]]
          </cr-button>
          <cr-button on-click="onFirefoxSyncNow_"
              hidden="[[!showSyncNow_(firefoxSync_)]]"
              disabled="[[firefoxSync_.syncing]]">
            [[i18n('firefoxSyncSyncNow')]]
          </cr-button>
          <cr-button id="firefoxSyncSignOut" on-click="onFirefoxSyncSignOut_"
              hidden="[[!firefoxSync_.signedIn]]">
            [[i18n('firefoxSyncSignOut')]]
          </cr-button>
        </div>
        <cr-link-row id="firefoxSyncTabs" class="hr" external
            label="[[i18n('firefoxSyncOtherDevicesTabs')]]"
            hidden="[[!showTabsLink_(firefoxSync_)]]"
            on-click="onFirefoxSyncTabs_">
        </cr-link-row>
        <cr-expand-button id="firefoxSyncTypesButton" class="cr-row"
            expanded="{{typesExpanded_}}">
          <div>[[i18n('firefoxSyncManage')]]</div>
        </cr-expand-button>
        <cr-collapse opened="[[typesExpanded_]]">
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
        </cr-collapse>
        <cr-expand-button id="firefoxSyncServersButton" class="cr-row"
            expanded="{{serversExpanded_}}">
          <div class="cr-padded-text">
            <div>[[i18n('firefoxSyncServers')]]</div>
            <div class="secondary">[[serversSummary_(firefoxSync_)]]</div>
          </div>
        </cr-expand-button>
        <cr-collapse opened="[[serversExpanded_]]">
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
        </cr-collapse>
        <cr-link-row id="firefoxSyncImport" class="hr"
            label="[[i18n('importTitle')]]" on-click="onImport_">
        </cr-link-row>
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
      avatar_: String,
      typesExpanded_: Boolean,
      serversExpanded_: Boolean,
    };
  }

  declare private firefoxSync_: FirefoxSyncStatus;
  declare private firefoxSyncServer_: string;
  declare private firefoxSyncStorageServer_: string;
  declare private avatar_: string;
  declare private typesExpanded_: boolean;
  declare private serversExpanded_: boolean;

  override connectedCallback() {
    super.connectedCallback();
    const setFirefoxSync = (status: FirefoxSyncStatus) => {
      if (status.server !== this.firefoxSync_.server) {
        this.firefoxSyncServer_ = status.server || '';
      }
      if (status.syncServer !== this.firefoxSync_.syncServer) {
        this.firefoxSyncStorageServer_ = status.syncServer || '';
      }
      // Without a server there's no signing in: open the fields.
      if (!status.signedIn && status.available && !status.canSignIn) {
        this.serversExpanded_ = true;
      }
      this.firefoxSync_ = status;
    };
    sendWithPromise<FirefoxSyncStatus>('getFirefoxSyncStatus')
        .then(setFirefoxSync);
    this.addWebUiListener('firefox-sync-status-changed', setFirefoxSync);
    const setAvatar = (info: ProfileInfo) => {
      this.avatar_ = info.iconUrl;
    };
    ProfileInfoBrowserProxyImpl.getInstance().getProfileInfo().then(setAvatar);
    this.addWebUiListener('profile-info-changed', setAvatar);
  }

  private firefoxSyncTitle_(status: FirefoxSyncStatus): string {
    if (!status.signedIn) {
      return this.i18n('firefoxSyncTitle');
    }
    return status.name || status.email || '';
  }

  // The email goes under a display name; without one it is the title.
  private showEmail_(status: FirefoxSyncStatus): boolean {
    return !!status.signedIn && !!status.name && !!status.email;
  }

  private pausedClass_(status: FirefoxSyncStatus): string {
    return status.signedIn && status.needsSignIn ? 'paused' : '';
  }

  private firefoxSyncDetail_(status: FirefoxSyncStatus): string {
    if (status.syncing) {
      return this.i18n('firefoxSyncSyncing');
    }
    if (status.signingIn) {
      return this.i18n('firefoxSyncSigningIn');
    }
    if (status.signedIn && status.needsSignIn) {
      return this.i18n('firefoxSyncPaused');
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

  private serversSummary_(status: FirefoxSyncStatus): string {
    if (!status.server) {
      return this.i18n('firefoxSyncNoServer');
    }
    const host = (url: string) => {
      try {
        return new URL(url).host;
      } catch {
        return url;
      }
    };
    return status.syncServer ?
        `${host(status.server)}, ${host(status.syncServer)}` :
        host(status.server);
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

  private signInLabel_(status: FirefoxSyncStatus): string {
    return this.i18n(
        status.signedIn ? 'firefoxSyncSignInAgain' : 'firefoxSyncSignIn');
  }

  private showSyncNow_(status: FirefoxSyncStatus): boolean {
    return !!status.signedIn && !status.needsSignIn;
  }

  private showTabsLink_(status: FirefoxSyncStatus): boolean {
    return !!status.signedIn &&
        !!status.types?.some(type => type.name === 'tabs' && type.enabled);
  }

  // The people page's import dialog; its section is hidden.
  private onImport_() {
    Router.getInstance().navigateTo(routes.IMPORT_DATA);
  }

  private onFirefoxSyncTabs_() {
    OpenWindowProxyImpl.getInstance().openUrl('chrome://history/syncedTabs');
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

  private onFirefoxSyncSignOut_() {
    chrome.send('firefoxSyncSignOut');
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
