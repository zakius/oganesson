// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// oganesson's setup, chrome://settings/setup, in place of Helium's
// chrome://setup: a full page over Settings (settings_ui.html), one step at a
// time. A first run shows every step. Afterwards, until browser traffic is
// chosen once for this OS user, startup opens it with ?existing: only Welcome,
// Browser traffic and Done. Every step but those two can be skipped, which
// keeps its default. Settings > About runs it again in full. Each step uses
// the handlers Settings already has.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_checkbox/cr_checkbox.js';
import 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '/shared/settings/prefs/prefs.js';
import '../privacy_page/browser_traffic_page.js';
import '../settings_shared.css.js';

import {PrefsMixin} from '/shared/settings/prefs/prefs_mixin.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {WebUiListenerMixin} from 'chrome://resources/cr_elements/web_ui_listener_mixin.js';
import {addWebUiListener, removeWebUiListener, sendWithPromise} from 'chrome://resources/js/cr.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {TAB_PRESETS} from '../appearance_page/tab_behavior.js';
import {DefaultBrowserBrowserProxyImpl} from '../default_browser_page/default_browser_browser_proxy.js';
import {loadTimeData} from '../i18n_setup.js';
import type {BrowserProfile} from '../people_page/import_data_browser_proxy.js';
import {ImportDataBrowserProxyImpl, ImportDataStatus} from '../people_page/import_data_browser_proxy.js';
import {Router} from '../router.js';
import type {SearchEngine} from '../search_page/search_engines_browser_proxy.js';
import {ChoiceMadeLocation, SearchEnginesBrowserProxyImpl} from '../search_page/search_engines_browser_proxy.js';

interface Step {
  id: string;
  label: string;
  // Shown also to a user who had the browser before.
  always?: boolean;
}

// helium::CrashReportingMode.
const CRASH_REPORTS_OFF = -1;
const CRASH_REPORTS_ASK = 0;

// The Google features step's opt-ins (goals.md, "Google features"), where
// Settings keeps them: Search engine, Languages > Translation, and System.
const LENS_PREF = 'oganesson.google.lens_enabled';
const CAST_PREF = 'oganesson.google.cast_enabled';
const TRANSLATE_PREF = 'oganesson.translate.enabled';
const TRANSLATE_ENGINE_PREF = 'oganesson.translate.engine';

// What each import checkbox sets, ImportDataHandler's keys.
const IMPORT_TYPES = [
  'import_dialog_bookmarks', 'import_dialog_history',
  'import_dialog_saved_passwords', 'import_dialog_extensions',
  'import_dialog_search_engine', 'import_dialog_autofill_form_data',
];

const SettingsSetupPageElementBase =
    PrefsMixin(I18nMixin(WebUiListenerMixin(PolymerElement)));

export class SettingsSetupPageElement extends SettingsSetupPageElementBase {
  static get is() {
    return 'settings-setup-page';
  }

  static get template() {
    return html`
      <style include="cr-shared-style settings-shared md-select">
        :host {
          align-items: flex-start;
          display: flex;
          justify-content: center;
          padding: 24px;
        }
        #window {
          background: var(--cr-card-background-color);
          border-radius: 8px;
          box-shadow: var(--cr-card-shadow);
          display: flex;
          max-width: 960px;
          min-height: 560px;
          width: 100%;
        }
        nav {
          border-inline-end: var(--cr-separator-line);
          flex: none;
          padding: 16px 10px;
          width: 170px;
        }
        nav div {
          border-radius: 4px;
          color: var(--cr-secondary-text-color);
          padding: 5px 8px;
        }
        nav div.current {
          background: var(--cr-hover-background-color);
          color: var(--cr-primary-text-color);
        }
        nav div.done::before {
          content: '✓ ';
        }
        main {
          display: flex;
          flex: 1;
          flex-direction: column;
          min-width: 0;
          padding: 20px 22px;
        }
        .content {
          flex: 1;
        }
        h2 {
          font-size: 20px;
          font-weight: 500;
          margin: 0 0 4px;
        }
        .lead {
          color: var(--cr-secondary-text-color);
          margin-bottom: 14px;
        }
        .note {
          border: 1px solid var(--cr-separator-color);
          border-radius: 4px;
          margin: 10px 0;
          padding: 10px 12px;
        }
        .cards {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          margin: 10px 0;
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
        .card b {
          display: block;
          font-weight: 500;
          margin-bottom: 4px;
        }
        .list cr-checkbox, .list .row {
          border-top: var(--cr-separator-line);
          padding: 9px 0;
        }
        .list > :first-child {
          border-top: none;
        }
        .row {
          align-items: center;
          display: flex;
          gap: 8px;
        }
        .flex {
          flex: 1;
        }
        .foot {
          align-items: center;
          display: flex;
          gap: 8px;
          justify-content: space-between;
          margin-top: 18px;
        }
        table {
          border-collapse: collapse;
          width: 100%;
        }
        td {
          border-top: var(--cr-separator-line);
          padding: 7px 5px;
        }
        td:first-child {
          color: var(--cr-secondary-text-color);
          width: 40%;
        }
        settings-browser-traffic {
          margin-inline: calc(-1 * var(--cr-section-padding));
        }
      </style>
      <!-- Settings keeps no prefs element of its own: each page has one. -->
      <settings-prefs id="prefs" prefs="{{prefs}}"></settings-prefs>
      <div id="window">
        <nav aria-hidden="true">
          <template is="dom-repeat" items="[[steps_]]" as="step">
            <div class$="[[navClass_(index, stepIndex_)]]">[[step.label]]</div>
          </template>
        </nav>
        <main>
          <div class="content">
            <template is="dom-if" if="[[is_(step_, 'welcome')]]" restamp>
              <template is="dom-if" if="[[!existing_]]" restamp>
                <h2>[[i18n('setupWelcomeTitle')]]</h2>
                <div class="lead">[[i18n('setupWelcomeLead')]]</div>
                <div class="note">[[welcomeNote_]]</div>
              </template>
              <template is="dom-if" if="[[existing_]]" restamp>
                <h2>[[i18n('setupNewChoiceTitle')]]</h2>
                <div class="lead">[[i18n('setupNewChoiceLead')]]</div>
                <div class="note">[[i18n('setupNewChoiceNote')]]</div>
              </template>
            </template>

            <template is="dom-if" if="[[is_(step_, 'import')]]" restamp>
              <h2>[[i18n('setupImportTitle')]]</h2>
              <div class="lead">[[i18n('setupImportFound')]]</div>
              <div class="list">
                <template is="dom-repeat" items="[[browsers_]]" as="browser">
                  <cr-checkbox checked="{{browser.selected}}">
                    [[browser.name]]
                    <div class="secondary">[[browser.profileName]]</div>
                  </cr-checkbox>
                </template>
                <div hidden="[[browsers_.length]]">
                  [[i18n('setupImportNone')]]
                </div>
              </div>
              <div class="lead" hidden="[[!browsers_.length]]">
                [[i18n('setupImportWhat')]]
              </div>
              <div class="list" hidden="[[!browsers_.length]]">
                <cr-checkbox checked="{{importBookmarks_}}">
                  [[i18n('setupImportBookmarks')]]
                </cr-checkbox>
                <cr-checkbox checked="{{importHistory_}}">
                  [[i18n('setupImportHistory')]]
                </cr-checkbox>
                <cr-checkbox checked="{{importPasswords_}}">
                  [[i18n('setupImportPasswords')]]
                  <div class="secondary">[[i18n('setupImportPasswordsNote')]]</div>
                </cr-checkbox>
                <cr-checkbox checked="{{importExtensions_}}">
                  [[i18n('setupImportExtensions')]]
                  <div class="secondary">[[extensionsNote_]]</div>
                </cr-checkbox>
              </div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'sync')]]" restamp>
              <h2>[[i18n('setupSyncTitle')]]</h2>
              <div class="lead">[[syncLead_]]</div>
              <div class="cards" role="radiogroup">
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[checked_(signIn_)]]" on-click="onSignInNow_">
                  <b>[[i18n('setupSyncNow')]]</b>
                  <div class="secondary">[[i18n('setupSyncNowDescription')]]</div>
                </div>
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[unchecked_(signIn_)]]" on-click="onSignInLater_">
                  <b>[[i18n('setupNotNow')]]</b>
                  <div class="secondary">
                    [[i18n('setupSyncLaterDescription')]]
                  </div>
                </div>
              </div>
            </template>

            <div hidden="[[!is_(step_, 'traffic')]]">
              <h2>[[i18n('setupTrafficTitle')]]</h2>
              <div class="lead">[[i18n('setupTrafficLead')]]</div>
              <settings-browser-traffic id="traffic" setup
                  can-continue="{{trafficReady_}}">
              </settings-browser-traffic>
            </div>

            <template is="dom-if" if="[[is_(step_, 'google')]]" restamp>
              <h2>[[i18n('setupStepGoogle')]]</h2>
              <div class="lead">[[i18n('setupGoogleLead')]]</div>
              <div class="list">
                <div class="row">
                  <div class="flex">
                    <div>[[i18n('googleLens')]]</div>
                    <div class="secondary">[[i18n('googleLensDescription')]]</div>
                  </div>
                  <cr-toggle id="googleLens" checked="[[lens_]]"
                      aria-label$="[[i18n('googleLens')]]"
                      on-change="onLensChange_"></cr-toggle>
                </div>
                <div class="row">
                  <div class="flex">
                    <div>[[i18n('oganessonTranslatePages')]]</div>
                    <div class="secondary">
                      [[i18n('oganessonTranslatePagesDescription')]]
                    </div>
                  </div>
                  <cr-toggle id="translatePages" checked="[[translate_]]"
                      aria-label$="[[i18n('oganessonTranslatePages')]]"
                      on-change="onTranslateChange_"></cr-toggle>
                </div>
              </div>
              <div id="translateEngine" class="cards" role="radiogroup"
                  hidden="[[!translate_]]">
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[isEngine_(translateEngine_, 'device')]]"
                    on-click="onDeviceEngine_">
                  <b>[[i18n('oganessonTranslateOnDevice')]]</b>
                  <div class="secondary">
                    [[i18n('oganessonTranslateOnDeviceDescription')]]
                  </div>
                </div>
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[isEngine_(translateEngine_, 'google')]]"
                    on-click="onGoogleEngine_">
                  <b>[[i18n('oganessonTranslateGoogle')]]</b>
                  <div class="secondary">
                    [[i18n('oganessonTranslateGoogleDescription')]]
                  </div>
                </div>
              </div>
              <div class="list">
                <div class="row">
                  <div class="flex">
                    <div>[[i18n('googleCast')]]</div>
                    <div class="secondary">[[i18n('googleCastDescription')]]</div>
                  </div>
                  <cr-toggle id="googleCast" checked="[[cast_]]"
                      aria-label$="[[i18n('googleCast')]]"
                      on-change="onCastChange_"></cr-toggle>
                </div>
              </div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'search')]]" restamp>
              <h2>[[i18n('setupSearchTitle')]]</h2>
              <div class="lead">[[i18n('setupSearchLead')]]</div>
              <div class="cards" role="radiogroup">
                <template is="dom-repeat" items="[[engines_]]" as="engine">
                  <div class="card" role="radio" tabindex="0"
                      aria-checked$="[[checked_(engine.default)]]"
                      on-click="onEngine_">
                    <b>[[engine.displayName]]</b>
                  </div>
                </template>
              </div>
              <div class="secondary">[[bangsNote_]]</div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'tabs')]]" restamp>
              <h2>[[i18n('setupTabsTitle')]]</h2>
              <div class="lead">[[i18n('setupTabsLead')]]</div>
              <div class="cards" role="radiogroup">
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[isTabs_(tabs_, 'firefox')]]"
                    on-click="onFirefoxTabs_">
                  <b>Firefox</b>
                  <div class="secondary">[[i18n('setupTabsFirefox')]]</div>
                </div>
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[isTabs_(tabs_, 'chromium')]]"
                    on-click="onChromiumTabs_">
                  <b>Chromium</b>
                  <div class="secondary">[[chromiumTabs_]]</div>
                </div>
              </div>
              <div class="secondary">[[i18n('setupTabsNote')]]</div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'passwords')]]" restamp>
              <h2>[[i18n('setupStepPasswords')]]</h2>
              <div class="lead">[[i18n('setupPasswordsLead')]]</div>
              <div class="cards" role="radiogroup">
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[checked_(savePasswords_)]]"
                    on-click="onSavePasswords_">
                  <b>[[i18n('setupPasswordsSave')]]</b>
                  <div class="secondary">
                    [[i18n('setupPasswordsSaveDescription')]]
                  </div>
                </div>
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[unchecked_(savePasswords_)]]"
                    on-click="onDontSavePasswords_">
                  <b>[[i18n('setupPasswordsDontSave')]]</b>
                  <div class="secondary">
                    [[i18n('setupPasswordsDontSaveDescription')]]
                  </div>
                </div>
              </div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'privacy')]]" restamp>
              <h2>[[i18n('setupStepPrivacy')]]</h2>
              <div class="list">
                <div class="row">
                  <div class="flex">
                    <div>[[i18n('setupCrashReports')]]</div>
                    <div class="secondary">[[crashDescription_]]</div>
                  </div>
                  <select class="md-select"
                      aria-label$="[[i18n('setupCrashReports')]]"
                      value="[[crashMode_]]" on-change="onCrashModeChange_">
                    <option value="-1">[[i18n('setupOff')]]</option>
                    <option value="0">[[i18n('setupAskEachTime')]]</option>
                  </select>
                </div>
                <cr-checkbox checked="[[noise_]]" on-change="onNoiseChange_">
                  [[i18n('setupNoise')]]
                  <div class="secondary">[[i18n('setupNoiseDescription')]]</div>
                </cr-checkbox>
              </div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'default')]]" restamp>
              <h2>[[i18n('setupDefaultTitle')]]</h2>
              <div class="lead">
                [[i18n('setupDefaultLead')]] [[defaultHow_]]
              </div>
              <div class="cards" role="radiogroup">
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[checked_(makeDefault_)]]" on-click="onMakeDefault_">
                  <b>[[i18n('setupMakeDefault')]]</b>
                </div>
                <div class="card" role="radio" tabindex="0"
                    aria-checked$="[[unchecked_(makeDefault_)]]"
                    on-click="onNotDefault_">
                  <b>[[i18n('setupNotNow')]]</b>
                </div>
              </div>
            </template>

            <template is="dom-if" if="[[is_(step_, 'done')]]" restamp>
              <h2>[[i18n('setupDoneTitle')]]</h2>
              <div class="lead">[[i18n('setupDoneLead')]]</div>
              <table>
                <template is="dom-repeat" items="[[summary_]]" as="line">
                  <tr><td>[[line.0]]</td><td>[[line.1]]</td></tr>
                </template>
              </table>
            </template>
          </div>
          <div class="foot">
            <div>
              <cr-button id="back" hidden="[[!stepIndex_]]" on-click="onBack_">
                [[i18n('setupBack')]]
              </cr-button>
            </div>
            <div class="row">
              <cr-button id="skip" class="tonal-button"
                  hidden="[[!canSkip_(step_)]]" on-click="onSkip_">
                [[i18n('setupSkip')]]
              </cr-button>
              <span class="secondary" hidden="[[!blocked_(step_, trafficReady_)]]">
                [[i18n('browserTrafficTestToContinue')]]
              </span>
              <cr-button id="next" class="action-button"
                  disabled="[[blocked_(step_, trafficReady_)]]"
                  on-click="onNext_">
                [[nextLabel_(stepIndex_, steps_)]]
              </cr-button>
            </div>
          </div>
        </main>
      </div>`;
  }

  static get properties() {
    return {
      steps_: {type: Array, value: () => []},
      stepIndex_: {type: Number, value: 0},
      step_: {type: String, computed: 'computeStep_(steps_, stepIndex_)'},
      existing_: Boolean,
      browsers_: {type: Array, value: () => []},
      importBookmarks_: {type: Boolean, value: true},
      importHistory_: {type: Boolean, value: true},
      importPasswords_: {type: Boolean, value: true},
      importExtensions_: {type: Boolean, value: false},
      imported_: {type: Array, value: () => []},
      signIn_: {
        type: Boolean,
        value: false,
      },
      trafficReady_: {
        type: Boolean,
        value: false,
      },
      engines_: {type: Array, value: () => []},
      tabs_: String,
      savePasswords_: Boolean,
      crashMode_: {type: String, value: String(CRASH_REPORTS_OFF)},
      noise_: Boolean,
      lens_: Boolean,
      translate_: Boolean,
      translateEngine_: String,
      cast_: Boolean,
      makeDefault_: {
        type: Boolean,
        value: false,
      },
      summary_: Array,
      bangsNote_: String,
      welcomeNote_: {
        type: String,
        value: () => loadTimeData.getStringF('setupWelcomeNote', 'Helium'),
      },
      extensionsNote_: {
        type: String,
        value: () => loadTimeData.getStringF('setupImportExtensionsNote',
                                             'Chrome Web Store'),
      },
      syncLead_: {
        type: String,
        value: () => loadTimeData.getStringF('setupSyncLead', 'Helium'),
      },
      chromiumTabs_: {
        type: String,
        value: () => loadTimeData.getStringF('setupTabsChromium', 'Chromium'),
      },
      crashDescription_: {
        type: String,
        value: () =>
            loadTimeData.getStringF('setupCrashReportsDescription', 'Helium'),
      },
      defaultHow_: String,
    };
  }

  declare private steps_: Step[];
  declare private stepIndex_: number;
  declare private step_: string;
  declare private existing_: boolean;
  declare private browsers_: Array<BrowserProfile&{selected: boolean}>;
  declare private importBookmarks_: boolean;
  declare private importHistory_: boolean;
  declare private importPasswords_: boolean;
  declare private importExtensions_: boolean;
  declare private imported_: string[];
  declare private signIn_: boolean;
  declare private trafficReady_: boolean;
  declare private engines_: SearchEngine[];
  declare private tabs_: string;
  declare private savePasswords_: boolean;
  declare private crashMode_: string;
  declare private noise_: boolean;
  declare private lens_: boolean;
  declare private translate_: boolean;
  declare private translateEngine_: string;
  declare private cast_: boolean;
  declare private makeDefault_: boolean;
  declare private summary_: Array<[string, string]>;
  declare private bangsNote_: string;
  declare private welcomeNote_: string;
  declare private extensionsNote_: string;
  declare private syncLead_: string;
  declare private chromiumTabs_: string;
  declare private crashDescription_: string;
  declare private defaultHow_: string;

  override connectedCallback() {
    super.connectedCallback();
    this.existing_ =
        Router.getInstance().getQueryParameters().has('existing');
    const all: Step[] = [
      {id: 'welcome', label: this.i18n('setupStepWelcome'), always: true},
      {id: 'import', label: this.i18n('setupStepImport')},
      ...(loadTimeData.valueExists('firefoxSyncSectionTitle') ?
              [{id: 'sync', label: this.i18n('setupStepSync')}] :
              []),
      {id: 'traffic', label: this.i18n('browserTrafficTitle'), always: true},
      {id: 'google', label: this.i18n('setupStepGoogle')},
      {id: 'search', label: this.i18n('setupStepSearch')},
      {id: 'tabs', label: this.i18n('setupStepTabs')},
      {id: 'passwords', label: this.i18n('setupStepPasswords')},
      {id: 'privacy', label: this.i18n('setupStepPrivacy')},
      {id: 'default', label: this.i18n('setupStepDefaultBrowser')},
      {id: 'done', label: this.i18n('setupStepDone'), always: true},
    ];
    this.steps_ = all.filter(step => !this.existing_ || step.always);

    ImportDataBrowserProxyImpl.getInstance().initializeImportDialog().then(
        browsers => this.browsers_ =
            browsers.map(browser => ({...browser, selected: false})));
    this.loadEngines_();
    sendWithPromise<{mode: number}>('getHeliumCrashReporting')
        .then(state => this.crashMode_ = String(state.mode));
    sendWithPromise<{browserUpdates: string}>('getBrowserTraffic')
        .then(state => this.defaultHow_ = this.i18n(
                  state.browserUpdates === 'packageManager' ?
                      'setupDefaultLinux' :
                      'setupDefaultWindows'));
  }

  // The prefs come with the prefs element, after connectedCallback.
  static get observers() {
    return ['prefsChanged_(prefs.*)'];
  }

  private prefsChanged_() {
    const tabs = Object.entries(TAB_PRESETS).find(
        ([, knobs]) => Object.entries(knobs).every(
            ([key, value]) => this.getPref(key)?.value === value));
    this.tabs_ = tabs ? tabs[0] : '';
    this.savePasswords_ =
        !!this.getPref('credentials_enable_service')?.value;
    this.noise_ = !!this.getPref('helium.noise.enabled')?.value;
    this.lens_ = !!this.getPref(LENS_PREF)?.value;
    this.translate_ = !!this.getPref(TRANSLATE_PREF)?.value;
    this.translateEngine_ = this.getPref<string>(TRANSLATE_ENGINE_PREF)?.value;
    this.cast_ = !!this.getPref(CAST_PREF)?.value;
  }

  private loadEngines_() {
    SearchEnginesBrowserProxyImpl.getInstance().getSearchEnginesList().then(
        list => this.engines_ = list.defaults.filter(e => e.canBeDefault)
                                    .slice(0, 6));
  }

  private computeStep_(steps: Step[], index: number): string {
    // Empty until connectedCallback picks the steps.
    return index < steps.length ? steps[index].id : '';
  }

  private is_(step: string, id: string): boolean {
    return step === id;
  }

  private navClass_(index: number, current: number): string {
    return index === current ? 'current' : index < current ? 'done' : '';
  }

  private canSkip_(step: string): boolean {
    return !['welcome', 'traffic', 'done'].includes(step);
  }

  private blocked_(step: string, trafficReady: boolean): boolean {
    return step === 'traffic' && !trafficReady;
  }

  private nextLabel_(index: number, steps: Step[]): string {
    if (index === steps.length - 1) {
      return this.i18n('setupStartBrowsing');
    }
    return this.i18n(index === 0 ? 'setupGetStarted' : 'setupNext');
  }

  // ARIA wants "true" or "false"; Polymer writes a boolean as an empty
  // attribute or none.
  private checked_(on: boolean): string {
    return String(on);
  }

  private unchecked_(on: boolean): string {
    return String(!on);
  }

  private isTabs_(tabs: string, preset: string): string {
    return String(tabs === preset);
  }

  private isEngine_(engine: string, name: string): string {
    return String(engine === name);
  }

  private onBack_() {
    this.stepIndex_--;
  }

  private onSkip_() {
    this.go_();
  }

  // Next applies the step's choice, then goes on.
  private onNext_() {
    switch (this.step_) {
      case 'import':
        this.import_();
        break;
      case 'sync':
        if (this.signIn_) {
          chrome.send('firefoxSyncSignIn');
        }
        break;
      case 'traffic':
        chrome.send('chooseBrowserTraffic');
        break;
      case 'default':
        if (this.makeDefault_) {
          DefaultBrowserBrowserProxyImpl.getInstance().setAsDefaultBrowser(
              false);
        }
        break;
      case 'done':
        window.location.href = 'chrome://newtab/';
        return;
    }
    this.go_();
  }

  private go_() {
    this.stepIndex_++;
    if (this.step_ === 'search') {
      this.updateBangsNote_();
    } else if (this.step_ === 'done') {
      this.summarize_();
    }
  }

  // One browser after another: the handler runs one import at a time.
  private async import_() {
    const types: {[type: string]: boolean} = {};
    for (const type of IMPORT_TYPES) {
      types[type] = false;
    }
    types['import_dialog_bookmarks'] = this.importBookmarks_;
    types['import_dialog_history'] = this.importHistory_;
    types['import_dialog_saved_passwords'] = this.importPasswords_;
    types['import_dialog_extensions'] = this.importExtensions_;
    const proxy = ImportDataBrowserProxyImpl.getInstance();
    for (const browser of this.browsers_.filter(b => b.selected)) {
      const finished = new Promise<void>(resolve => {
        const listener = addWebUiListener(
            'import-data-status-changed', (status: ImportDataStatus) => {
              if (status === ImportDataStatus.SUCCEEDED ||
                  status === ImportDataStatus.FAILED) {
                removeWebUiListener(listener);
                resolve();
              }
            });
      });
      proxy.importData(browser.index, {
        ...types,
        import_dialog_extensions: types['import_dialog_extensions'] &&
            browser.extensions,
      });
      this.imported_ = [...this.imported_, browser.name];
      await finished;
    }
  }

  private onSignInNow_() {
    this.signIn_ = true;
  }

  private onSignInLater_() {
    this.signIn_ = false;
  }

  private onEngine_(e: Event&{model: {engine: SearchEngine}}) {
    SearchEnginesBrowserProxyImpl.getInstance().setDefaultSearchEngine(
        e.model.engine.id,
        ChoiceMadeLocation.SEARCH_ENGINE_SETTINGS, null);
    this.engines_ = this.engines_.map(
        engine => ({...engine, default: engine.id === e.model.engine.id}));
  }

  private async updateBangsNote_() {
    const state = await sendWithPromise<
        {server: string, rows: Array<{name: string, automatic: boolean}>}>(
        'getBrowserTraffic');
    const bangs = state.rows.find(row => row.name === 'bangs');
    this.bangsNote_ = this.i18n(
        bangs?.automatic && state.server ? 'setupBangsOn' : 'setupBangsOff');
  }

  private setTabs_(preset: string) {
    for (const [key, value] of Object.entries(TAB_PRESETS[preset])) {
      this.setPrefValue(key, value);
    }
  }

  private onFirefoxTabs_() {
    this.setTabs_('firefox');
  }

  private onChromiumTabs_() {
    this.setTabs_('chromium');
  }

  private onSavePasswords_() {
    this.setPrefValue('credentials_enable_service', true);
  }

  private onDontSavePasswords_() {
    this.setPrefValue('credentials_enable_service', false);
  }

  private onCrashModeChange_(e: Event) {
    this.crashMode_ = (e.target as HTMLSelectElement).value;
    chrome.send('setHeliumCrashReportingMode', [Number(this.crashMode_)]);
  }

  private onNoiseChange_(e: Event) {
    this.setPrefValue('helium.noise.enabled',
                      (e.target as HTMLInputElement).checked);
  }

  private onLensChange_(e: CustomEvent<boolean>) {
    this.setPrefValue(LENS_PREF, e.detail);
  }

  private onTranslateChange_(e: CustomEvent<boolean>) {
    this.setPrefValue(TRANSLATE_PREF, e.detail);
  }

  private onCastChange_(e: CustomEvent<boolean>) {
    this.setPrefValue(CAST_PREF, e.detail);
  }

  private onDeviceEngine_() {
    this.setPrefValue(TRANSLATE_ENGINE_PREF, 'device');
  }

  private onGoogleEngine_() {
    this.setPrefValue(TRANSLATE_ENGINE_PREF, 'google');
  }

  private onMakeDefault_() {
    this.makeDefault_ = true;
  }

  private onNotDefault_() {
    this.makeDefault_ = false;
  }

  private async summarize_() {
    const traffic = await sendWithPromise<{preset: string, server: string,
                                           needsServer: boolean}>(
        'getBrowserTraffic');
    const preset = this.i18n(`browserTrafficPreset${
        traffic.preset.charAt(0).toUpperCase() + traffic.preset.slice(1)}`);
    const lines: Array<[string, string]> = [[
      this.i18n('browserTrafficTitle'),
      traffic.needsServer ?
          loadTimeData.getStringF('setupTrafficServer', preset,
                                  traffic.server || this.i18n('setupNotSet')) :
          preset,
    ]];
    if (!this.existing_) {
      const engine = this.engines_.find(e => e.default);
      lines.unshift(
          [this.i18n('setupStepImport'),
           this.imported_.join(', ') || this.i18n('setupNothing')]);
      if (this.steps_.some(step => step.id === 'sync')) {
        lines.splice(1, 0, [
          this.i18n('setupStepSync'),
          this.i18n(this.signIn_ ? 'setupSigningIn' : 'setupNotNow'),
        ]);
      }
      lines.push(
          [this.i18n('googleLens'),
           this.i18n(this.lens_ ? 'setupOn' : 'setupOff')],
          [this.i18n('oganessonTranslatePages'),
           this.i18n(!this.translate_ ? 'setupOff' :
                     this.translateEngine_ === 'google' ?
                                         'oganessonTranslateGoogle' :
                                         'oganessonTranslateOnDevice')],
          [this.i18n('googleCast'),
           this.i18n(this.cast_ ? 'setupOn' : 'setupOff')],
          [this.i18n('setupStepSearch'), engine ? engine.displayName : ''],
          [this.i18n('setupStepTabs'),
           this.tabs_ === 'firefox' ? 'Firefox' :
           this.tabs_ === 'chromium' ? 'Chromium' :
                                       this.i18n('tabBehaviorCustom')],
          [this.i18n('setupStepPasswords'),
           this.i18n(this.savePasswords_ ? 'setupSavedInBrowser' :
                                           'setupNotSaved')],
          [this.i18n('setupCrashReports'),
           this.i18n(Number(this.crashMode_) === CRASH_REPORTS_ASK ?
                         'setupAskEachTime' :
                         'setupOff')],
          [this.i18n('setupNoise'),
           this.i18n(this.noise_ ? 'setupOn' : 'setupOff')],
          [this.i18n('setupStepDefaultBrowser'),
           this.i18n(this.makeDefault_ ? 'setupYes' : 'setupNotNow')]);
    }
    this.summary_ = lines;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-setup-page': SettingsSetupPageElement;
  }
}

customElements.define(SettingsSetupPageElement.is, SettingsSetupPageElement);
