// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Settings > Privacy and security > Browser traffic: what the browser
// downloads by itself, and which way it goes. A preset over the rows, as Tab
// behavior's: the preset is derived from the rows, and Custom shows when they
// match none. Talks to BrowserTrafficHandler, which applies dubna's rules
// (components/browser_traffic). settings-browser-traffic is the page's body,
// which setup's Browser traffic step shows too, with `setup`: presets as cards,
// and the server only when a row needs it.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '../settings_page/settings_subpage.js';
import '../settings_shared.css.js';

import type {CrInputElement} from 'chrome://resources/cr_elements/cr_input/cr_input.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {WebUiListenerMixin} from 'chrome://resources/cr_elements/web_ui_listener_mixin.js';
import {sendWithPromise} from 'chrome://resources/js/cr.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {loadTimeData} from '../i18n_setup.js';

/** From BrowserTrafficHandler (oganesson). */
interface BrowserTrafficRow {
  name: string;
  automatic: boolean;
  proxy: boolean;
  hasDirect: boolean;
  hasProxy: boolean;
  // Proxied, with no valid server.
  idle: boolean;
}

interface BrowserTrafficState {
  rows: BrowserTrafficRow[];
  preset: string;
  server: string;
  needsServer: boolean;
  healthPeriodic: boolean;
  // Milliseconds since the epoch, 0 for never.
  serverAnswered: number;
  serverFailed: number;
  certificatesUpdated: number;
  // 'row', 'managed' (a Windows all-users install) or 'packageManager'.
  browserUpdates: string;
}

// Events from the dom-repeats, whose items are named by `as`.
type PresetEvent<E extends Event = Event> = E&{model: {preset: string}};
type RowEvent = Event&{model: {row: BrowserTrafficRow}};

// Where each direct row's data comes from: names, not translated.
const SOURCES: Record<string, string> = {
  certificates: 'Google',
  drm: 'Google',
  extensions: 'Chrome Web Store',
  dictionaries: 'Google',
  browser_updates: 'dubna.zakius.xyz',
};

// Rows with an Update now button while they are On request.
const UPDATE_NOW = ['certificates', 'bangs'];

function capitalized(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function relativeTime(time: number): string {
  const seconds = (time - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat(document.documentElement.lang,
                                             {numeric: 'auto'});
  for (const [unit, size] of [['day', 86400], ['hour', 3600],
                              ['minute', 60]] as Array<[Intl.RelativeTimeFormatUnit, number]>) {
    if (Math.abs(seconds) >= size) {
      return format.format(Math.round(seconds / size), unit);
    }
  }
  return format.format(0, 'minute');
}

function timeOfDay(time: number): string {
  return new Date(time).toLocaleTimeString(document.documentElement.lang,
                                           {hour: '2-digit', minute: '2-digit'});
}

const PRESET_CARDS = ['direct', 'throughServer', 'shutIn', 'custom'];

const BrowserTrafficElementBase =
    I18nMixin(WebUiListenerMixin(PolymerElement));

export class BrowserTrafficElement extends BrowserTrafficElementBase {
  static get is() {
    return 'settings-browser-traffic';
  }

  static get template() {
    return html`
      <style include="cr-shared-style settings-shared md-select">
        .warning {
          border: 1px solid currentColor;
          border-radius: 4px;
          margin: 8px var(--cr-section-padding);
          padding: 10px 12px;
        }
        .warning.red {
          color: var(--cr-fallback-color-error, var(--google-red-600));
        }
        .warning.yellow {
          color: var(--cr-fallback-color-warning, var(--google-yellow-700));
        }
        .warning b {
          font-weight: 500;
        }
        .bad {
          color: var(--cr-fallback-color-error, var(--google-red-600));
        }
        .good {
          color: var(--cr-fallback-color-success, var(--google-green-700));
        }
        .fixed {
          color: var(--cr-secondary-text-color);
          text-align: end;
        }
        .row-controls {
          align-items: center;
          display: flex;
          gap: 8px;
        }
        .row-controls .md-select {
          --md-select-width: 140px;
        }
        #serverRow cr-input {
          flex: 1;
        }
        #body {
          display: flex;
          flex-direction: column;
        }
        #body.setup #serverSection {
          order: 1;
        }
        .cards {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          margin: 10px var(--cr-section-padding);
        }
        .cards[hidden] {
          display: none;
        }
        .card {
          border: 1px solid var(--cr-separator-color);
          border-radius: 8px;
          cursor: pointer;
          padding: 12px;
        }
        .card[aria-checked=true] {
          border-color: var(--cr-checked-color);
          box-shadow: 0 0 0 1px var(--cr-checked-color);
        }
        .card[aria-disabled=true] {
          cursor: default;
        }
        .card b {
          display: block;
          font-weight: 500;
          margin-bottom: 4px;
        }
      </style>
      <div id="body" class$="[[bodyClass_(setup)]]">
        <div class="cr-row first" hidden="[[setup]]">
          <div class="cr-padded-text secondary">
            [[i18n('browserTrafficDescription')]]
          </div>
        </div>

        <div id="serverSection" hidden="[[!showServer_(setup, state_)]]">
        <div class="cr-row">
          <div class="flex cr-padded-text">
            <div>[[i18n('browserTrafficServer')]]</div>
            <div class="secondary">[[serverDescription_]]</div>
          </div>
        </div>
        <div id="serverRow" class="cr-row row-controls">
          <cr-input id="server" value="[[state_.server]]"
              placeholder="[[i18n('browserTrafficServerNotSet')]]"
              aria-label="[[i18n('browserTrafficServer')]]"
              invalid="[[serverInvalid_]]"
              error-message="[[i18n('browserTrafficServerInvalid')]]"
              spellcheck="false" on-change="onServerChange_"
              on-input="onServerInput_">
          </cr-input>
          <cr-button id="test" on-click="onTest_">
            [[i18n('browserTrafficTest')]]
          </cr-button>
        </div>
        <div class="cr-row continuation">
          <div id="serverStatus" class="cr-padded-text secondary">
            <span class$="[[statusClass_(state_)]]">[[status_(state_)]]</span>
            <span id="testResult" class$="[[testClass_]]">[[testResult_]]</span>
          </div>
        </div>
        <template is="dom-if" if="[[state_.needsServer]]" restamp>
          <div id="healthCheck" class="cr-row">
            <div class="flex cr-padded-text">
              <div>[[i18n('browserTrafficHealthCheck')]]</div>
              <div class="secondary">
                [[i18n('browserTrafficHealthCheckDescription')]]
              </div>
            </div>
            <div class="row-controls">
              <select class="md-select"
                  aria-label$="[[i18n('browserTrafficHealthCheck')]]"
                  value="[[healthValue_(state_)]]"
                  on-change="onHealthCheckChange_">
                <option value="periodically">
                  [[i18n('browserTrafficPeriodically')]]
                </option>
                <option value="onRequest">
                  [[i18n('browserTrafficOnRequest')]]
                </option>
              </select>
              <cr-button on-click="onCheckNow_">
                [[i18n('browserTrafficCheckNow')]]
              </cr-button>
            </div>
          </div>
        </template>
        </div>

        <template is="dom-if" if="[[serverDown_(state_)]]" restamp>
          <div id="serverDown" class="warning yellow">
            <b>[[serverDownTitle_(state_)]]</b> [[serverDown_(state_)]]
          </div>
        </template>

        <div id="presetCards" class="cards" role="radiogroup" hidden="[[!setup]]">
          <template is="dom-repeat" items="[[presetCards_]]" as="preset">
            <div class="card" role="radio" tabindex$="[[cardTabIndex_(preset)]]"
                aria-checked$="[[isPreset_(preset, state_)]]"
                aria-disabled$="[[isCustom_(preset)]]"
                on-click="onPresetCard_" on-keydown="onPresetCardKey_">
              <b>[[presetName_(preset)]]</b>
              <div class="secondary">[[presetDescriptionOf_(preset)]]</div>
            </div>
          </template>
        </div>
        <div class="cr-row" hidden="[[setup]]">
          <div class="flex cr-padded-text" aria-hidden="true">
            [[i18n('browserTrafficPreset')]]
          </div>
          <select id="preset" class="md-select"
              aria-label$="[[i18n('browserTrafficPreset')]]"
              value="[[state_.preset]]" on-change="onPresetChange_">
            <option value="direct">[[i18n('browserTrafficPresetDirect')]]</option>
            <option value="throughServer">
              [[i18n('browserTrafficPresetThroughServer')]]
            </option>
            <option value="shutIn">[[i18n('browserTrafficPresetShutIn')]]</option>
            <option value="custom" disabled>
              [[i18n('browserTrafficPresetCustom')]]
            </option>
          </select>
        </div>
        <div class="cr-row continuation" hidden="[[setup]]">
          <div class="cr-padded-text secondary">
            [[presetDescription_(state_)]]
          </div>
        </div>

        <template is="dom-if" if="[[revocationWarning_(state_)]]" restamp>
          <div id="revocationWarning" class="warning red">
            <b>[[i18n('browserTrafficRevocationWarningTitle')]]</b>
            [[revocationWarning_(state_)]]
          </div>
        </template>

        <div class="list-frame">
          <div class="cr-row first">
            <div class="flex secondary">[[i18n('browserTrafficWhat')]]</div>
            <div class="secondary">
              [[i18n('browserTrafficDownload')]] · [[i18n('browserTrafficRoute')]]
            </div>
          </div>
          <template is="dom-repeat" items="[[state_.rows]]" as="row">
            <div class="cr-row" id$="row_[[row.name]]">
              <div class="flex cr-padded-text">
                <div>[[rowName_(row)]]</div>
                <div class="secondary">
                  [[rowDetail_(row, state_)]]
                  <span class="bad" hidden="[[!row.idle]]">
                    · [[idleText_(row)]]
                  </span>
                </div>
              </div>
              <div class="row-controls">
                <cr-button hidden="[[!showUpdateNow_(row)]]"
                    on-click="onUpdateNow_">
                  [[i18n('browserTrafficUpdateNow')]]
                </cr-button>
                <select class="md-select download"
                    aria-label$="[[rowName_(row)]]: [[i18n('browserTrafficDownload')]]"
                    value="[[downloadValue_(row)]]"
                    on-change="onDownloadChange_">
                  <option value="automatic">
                    [[i18n('browserTrafficAutomatic')]]
                  </option>
                  <option value="onRequest">
                    [[i18n('browserTrafficOnRequest')]]
                  </option>
                </select>
                <select class="md-select route"
                    hidden="[[!hasBothRoutes_(row)]]"
                    aria-label$="[[rowName_(row)]]: [[i18n('browserTrafficRoute')]]"
                    value="[[routeValue_(row)]]" on-change="onRouteChange_">
                  <option value="direct">[[i18n('browserTrafficDirect')]]</option>
                  <option value="proxy">[[i18n('browserTrafficProxy')]]</option>
                </select>
                <div class="fixed" hidden="[[hasBothRoutes_(row)]]">
                  <div>[[onlyRoute_(row)]]</div>
                  <div class="secondary">[[onlyRouteWhy_(row, state_)]]</div>
                </div>
              </div>
            </div>
          </template>
          <template is="dom-if"
              if="[[isBrowserUpdates_(state_, 'managed')]]" restamp>
            <div id="managedUpdates" class="cr-row">
              <div class="flex cr-padded-text">
                <div>[[i18n('browserTrafficRow_browser_updates')]]</div>
                <div class="secondary">
                  [[i18n('browserTrafficBrowserUpdatesManaged')]]
                </div>
              </div>
            </div>
          </template>
        </div>
        <template is="dom-if"
            if="[[isBrowserUpdates_(state_, 'packageManager')]]" restamp>
          <div id="packageManager" class="cr-row continuation">
            <div class="cr-padded-text secondary">
              [[i18n('browserTrafficPackageManager')]]
            </div>
          </div>
        </template>
      </div>`;
  }

  static get properties() {
    return {
      // Setup's step: presets as cards, the server only when needed.
      setup: {
        type: Boolean,
        value: false,
      },

      // Whether setup may go on: no row needs the server, or the saved one
      // answered the test.
      canContinue: {
        type: Boolean,
        notify: true,
        computed: 'computeCanContinue_(state_, answeredServer_)',
      },

      presetCards_: {
        type: Array,
        value: () => PRESET_CARDS,
      },

      // The saved server that last answered Test.
      answeredServer_: {
        type: String,
        value: '',
      },

      state_: {
        type: Object,
        value: () => ({rows: [], preset: 'direct', server: ''}),
      },
      serverDescription_: {
        type: String,
        value: () => loadTimeData.getStringF('browserTrafficServerDescription',
                                             'helium-services'),
      },
      serverInvalid_: {
        type: Boolean,
        value: false,
      },
      testResult_: String,
      testClass_: String,
    };
  }

  declare setup: boolean;
  declare canContinue: boolean;
  declare private presetCards_: string[];
  declare private answeredServer_: string;
  declare private state_: BrowserTrafficState;
  declare private serverDescription_: string;
  declare private serverInvalid_: boolean;
  declare private testResult_: string;
  declare private testClass_: string;

  override connectedCallback() {
    super.connectedCallback();
    this.addWebUiListener('browser-traffic-changed',
                          (state: BrowserTrafficState) => this.state_ = state);
    sendWithPromise<BrowserTrafficState>('getBrowserTraffic')
        .then(state => this.state_ = state);
  }

  private presetDescription_(state: BrowserTrafficState): string {
    return this.presetDescriptionOf_(state.preset);
  }

  private presetName_(preset: string): string {
    return this.i18n(`browserTrafficPreset${capitalized(preset)}`);
  }

  private presetDescriptionOf_(preset: string): string {
    return this.i18n(`browserTrafficPreset${capitalized(preset)}Description`);
  }

  private isPreset_(preset: string, state: BrowserTrafficState): boolean {
    return preset === state.preset;
  }

  private isCustom_(preset: string): boolean {
    return preset === 'custom';
  }

  private cardTabIndex_(preset: string): number {
    return this.isCustom_(preset) ? -1 : 0;
  }

  private bodyClass_(setup: boolean): string {
    return setup ? 'setup' : '';
  }

  private showServer_(setup: boolean, state: BrowserTrafficState): boolean {
    return !setup || state.needsServer;
  }

  private computeCanContinue_(state: BrowserTrafficState,
                              answeredServer: string): boolean {
    return !state.needsServer ||
        (!!state.server && state.server === answeredServer);
  }

  private onPresetCard_(e: PresetEvent) {
    if (!this.isCustom_(e.model.preset)) {
      chrome.send('applyBrowserTrafficPreset', [e.model.preset]);
    }
  }

  private onPresetCardKey_(e: PresetEvent<KeyboardEvent>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      this.onPresetCard_(e);
    }
  }

  private rowName_(row: BrowserTrafficRow): string {
    return this.i18n(`browserTrafficRow_${row.name}`);
  }

  private rowDetail_(row: BrowserTrafficRow, state: BrowserTrafficState):
      string {
    let detail = this.i18n(`browserTrafficRowDescription_${row.name}`);
    if (!row.proxy && row.name === 'content_blocker') {
      detail += ' · ' + this.i18n('browserTrafficFromListAuthors');
    } else if (!row.proxy && SOURCES[row.name]) {
      detail += ' · ' +
          loadTimeData.getStringF('browserTrafficFrom', SOURCES[row.name]);
    }
    if (row.name === 'certificates' && state.certificatesUpdated) {
      detail += ' · ' +
          loadTimeData.getStringF('browserTrafficUpdated',
                                  relativeTime(state.certificatesUpdated));
    }
    return detail;
  }

  private idleText_(row: BrowserTrafficRow): string {
    return this.i18n(row.hasDirect ? 'browserTrafficIdle' :
                                     'browserTrafficOffWithoutServer');
  }

  private hasBothRoutes_(row: BrowserTrafficRow): boolean {
    return row.hasDirect && row.hasProxy;
  }

  private onlyRoute_(row: BrowserTrafficRow): string {
    return this.i18n(row.hasProxy ? 'browserTrafficProxyOnly' :
                                    'browserTrafficDirectOnly');
  }

  private onlyRouteWhy_(row: BrowserTrafficRow, state: BrowserTrafficState):
      string {
    if (!row.hasProxy) {
      return this.i18n('browserTrafficServerCantServe');
    }
    // An idle bangs row says so next to its name.
    return state.server ? this.i18n('browserTrafficNoDirectSource') : '';
  }

  private showUpdateNow_(row: BrowserTrafficRow): boolean {
    return !row.automatic && UPDATE_NOW.includes(row.name);
  }

  private downloadValue_(row: BrowserTrafficRow): string {
    return row.automatic ? 'automatic' : 'onRequest';
  }

  private routeValue_(row: BrowserTrafficRow): string {
    return row.proxy ? 'proxy' : 'direct';
  }

  private healthValue_(state: BrowserTrafficState): string {
    return state.healthPeriodic ? 'periodically' : 'onRequest';
  }

  private isBrowserUpdates_(state: BrowserTrafficState, kind: string):
      boolean {
    return state.browserUpdates === kind;
  }

  private revocationWarning_(state: BrowserTrafficState): string {
    const certificates = state.rows.find(row => row.name === 'certificates');
    return certificates && !certificates.automatic ?
        loadTimeData.getStringF('browserTrafficRevocationWarning', 'Chrome') :
        '';
  }

  // The server stopped answering: its last failure is newer than its last
  // answer.
  private isServerDown_(state: BrowserTrafficState): boolean {
    return state.needsServer && !!state.server &&
        state.serverFailed > state.serverAnswered;
  }

  private serverDownTitle_(state: BrowserTrafficState): string {
    return state.serverAnswered ?
        loadTimeData.getStringF('browserTrafficServerDownTitle',
                                timeOfDay(state.serverAnswered)) :
        this.i18n('browserTrafficStatusNeverAnswered');
  }

  private serverDown_(state: BrowserTrafficState): string {
    return this.isServerDown_(state) ?
        loadTimeData.getStringF('browserTrafficServerDown',
                                relativeTime(state.certificatesUpdated)) :
        '';
  }

  private status_(state: BrowserTrafficState): string {
    if (!state.server) {
      return this.i18n('browserTrafficServerNotSet');
    }
    if (this.isServerDown_(state) || (state.serverFailed && !state.serverAnswered)) {
      return state.serverAnswered ?
          loadTimeData.getStringF('browserTrafficStatusUnreachable',
                                  timeOfDay(state.serverAnswered)) :
          this.i18n('browserTrafficStatusNeverAnswered');
    }
    if (!state.serverAnswered) {
      return this.i18n('browserTrafficStatusUnchecked');
    }
    return loadTimeData.getStringF('browserTrafficStatusReachable',
                                   relativeTime(state.certificatesUpdated));
  }

  private statusClass_(state: BrowserTrafficState): string {
    if (!state.server || (!state.serverAnswered && !state.serverFailed)) {
      return '';
    }
    return state.serverFailed > state.serverAnswered ? 'bad' : 'good';
  }

  private onServerInput_() {
    this.serverInvalid_ = false;
    this.testResult_ = '';
  }

  private async onServerChange_(e: Event) {
    const input = e.target as CrInputElement;
    const saved = await sendWithPromise<boolean>(
        'setBrowserTrafficServer', input.value.trim());
    this.serverInvalid_ = !saved;
  }

  // Saves the field's address, then asks the saved server.
  private async onTest_() {
    const input =
        this.shadowRoot!.querySelector<CrInputElement>('#server')!;
    const saved = await sendWithPromise<boolean>(
        'setBrowserTrafficServer', input.value.trim());
    this.serverInvalid_ = !saved;
    if (saved) {
      await this.onCheckNow_();
    }
  }

  private async onCheckNow_() {
    this.testClass_ = '';
    const state =
        await sendWithPromise<BrowserTrafficState>('getBrowserTraffic');
    this.testResult_ = loadTimeData.getStringF(
        'browserTrafficTesting', `${state.server}connectivitycheck`);
    const answered =
        await sendWithPromise<boolean>('testBrowserTrafficServer', '');
    this.answeredServer_ = answered ? state.server : '';
    this.testClass_ = answered ? 'good' : 'bad';
    this.testResult_ = this.i18n(answered ? 'browserTrafficServerAnswered' :
                                            'browserTrafficServerNoAnswer');
  }

  private onHealthCheckChange_(e: Event) {
    chrome.send('setBrowserTrafficHealthCheck',
                [(e.target as HTMLSelectElement).value === 'periodically']);
  }

  private onPresetChange_(e: Event) {
    chrome.send('applyBrowserTrafficPreset',
                [(e.target as HTMLSelectElement).value]);
  }

  private onDownloadChange_(e: RowEvent) {
    const row = e.model.row;
    chrome.send('setBrowserTrafficRow', [
      row.name, (e.target as HTMLSelectElement).value === 'automatic',
      row.proxy,
    ]);
  }

  private onRouteChange_(e: RowEvent) {
    const row = e.model.row;
    chrome.send('setBrowserTrafficRow', [
      row.name, row.automatic,
      (e.target as HTMLSelectElement).value === 'proxy',
    ]);
  }

  private onUpdateNow_(e: RowEvent) {
    chrome.send('updateBrowserTrafficNow', [e.model.row.name]);
  }
}

customElements.define(BrowserTrafficElement.is, BrowserTrafficElement);

const SettingsBrowserTrafficPageElementBase = I18nMixin(PolymerElement);

export class SettingsBrowserTrafficPageElement extends
    SettingsBrowserTrafficPageElementBase {
  static get is() {
    return 'settings-browser-traffic-page';
  }

  static get template() {
    return html`
      <settings-subpage page-title="[[i18n('browserTrafficTitle')]]"
          route-path$="[[routePath]]">
        <settings-browser-traffic></settings-browser-traffic>
      </settings-subpage>`;
  }

  static get properties() {
    return {
      // Set by privacy_page_index.html, for settings-subpage.
      routePath: String,
    };
  }

  declare routePath: string;
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-browser-traffic': BrowserTrafficElement;
    'settings-browser-traffic-page': SettingsBrowserTrafficPageElement;
  }
}

customElements.define(SettingsBrowserTrafficPageElement.is,
                      SettingsBrowserTrafficPageElement);
