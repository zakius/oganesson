// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Mouse gestures on the "Shortcuts and gestures" page. The page places three
// elements: <settings-gesture-chips> and <settings-add-gesture> in each
// command row, and <settings-extension-gestures> after the commands. They
// keep their own state, so Helium's page only hosts them.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_dialog/cr_dialog.js';
import 'chrome://resources/cr_elements/cr_icon_button/cr_icon_button.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '../settings_shared.css.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {BrowserShortcutsHandlerFactory, BrowserShortcutsHandlerRemote, BrowserShortcutsPageCallbackRouter} from '../browser_shortcuts.mojom-webui.js';
import type {ExtensionCommand} from '../browser_shortcuts.mojom-webui.js';
import {loadTimeData} from '../i18n_setup.js';

// Maps mouse gestures to a GestureValue. Keys are stroke chains, such as "DR",
// or one of the non-stroke gestures below.
const GESTURES_PREF = 'oganesson.mouse_gestures';
const STROKE = 'stroke';

// A browser command id, or an extension command.
type GestureValue = number|{extension: string, command: string};

const GESTURE_LABELS: Record<string, string> = {
  'rocker-rl': 'shortcutsGestureRockerRightLeft',
  'rocker-lr': 'shortcutsGestureRockerLeftRight',
  'wheel-up': 'shortcutsGestureWheelUp',
  'wheel-down': 'shortcutsGestureWheelDown',
};

function isSameGestureValue(a: GestureValue, b: GestureValue): boolean {
  return typeof a === 'number' || typeof b === 'number' ?
      a === b :
      a.extension === b.extension && a.command === b.command;
}

function toGestureValue(command: ExtensionCommand): GestureValue {
  return {extension: command.extensionId, command: command.commandName};
}

// The recognizer collapses repeated directions, so "LL" can never match.
function normalizeGesture(chain: string): string|null {
  const normalized = chain.trim().toUpperCase();
  return /^[LRUD]{1,64}$/.test(normalized) && !/(.)\1/.test(normalized) ?
      normalized :
      null;
}

function getGestureLabel(gesture: string): string {
  if (gesture === STROKE) {
    return loadTimeData.getString('shortcutsGestureStroke');
  }
  const label = GESTURE_LABELS[gesture];
  return label ? loadTimeData.getString(label) : gesture;
}

function gesturesFor(
    value: GestureValue|null, gestures: Record<string, GestureValue>):
    string[] {
  return value === null ?
      [] :
      Object.keys(gestures)
          .filter(chain => isSameGestureValue(gestures[chain]!, value))
          .sort();
}

function newHandler(): BrowserShortcutsHandlerRemote {
  const handler = new BrowserShortcutsHandlerRemote();
  BrowserShortcutsHandlerFactory.getRemote().createBrowserShortcutsHandler(
      new BrowserShortcutsPageCallbackRouter().$.bindNewPipeAndPassRemote(),
      handler.$.bindNewPipeAndPassReceiver());
  return handler;
}

export function mouseGesturesEnabled(): boolean {
  return loadTimeData.getBoolean('showMouseGestures');
}

// The gestures last seen, for the page's search, which ranks a command by its
// gesture labels too.
let currentGestures: Record<string, GestureValue> = {};
PrefService.getInstance().addObserver<Record<string, GestureValue>>(
    GESTURES_PREF, pref => currentGestures = pref.value);

export function gestureSearchFields(commandId: number): string[] {
  return gesturesFor(commandId, currentGestures).map(getGestureLabel);
}

const CHIP_STYLE = html`
  <style include="cr-shared-style settings-shared md-select">
    :host {
      display: contents;
    }

    .shortcut-chip {
      align-items: center;
      background: var(--cr-hover-background-color);
      border: 1px solid transparent;
      border-radius: 8px;
      color: var(--cr-primary-text-color);
      display: inline-flex;
      font-size: 12px;
      font-weight: 500;
      line-height: 20px;
      min-height: 28px;
      overflow: hidden;
      padding-inline-end: 2px;
      padding-inline-start: 10px;
      white-space: nowrap;
    }

    .shortcut-label {
      align-items: center;
      display: inline-flex;
      height: 24px;
      line-height: 24px;
    }

    .shortcut-chip cr-icon-button {
      --cr-icon-button-icon-size: 16px;
      --cr-icon-button-margin-end: 0;
      --cr-icon-button-margin-start: 0;
      --cr-icon-button-size: 24px;
      flex-shrink: 0;
      margin-inline-start: 4px;
    }

    cr-button {
      --cr-button-height: 32px;
    }

    #gestureDescription,
    #gestureInput {
      margin-top: 12px;
    }

    .warning {
      color: var(--google-red-700);
      margin-top: 12px;
    }
  </style>`;

const GestureChipsElementBase = PrefServiceObserverMixin(PolymerElement);

// The gesture chips of one command, each with a remove button.
export class SettingsGestureChipsElement extends GestureChipsElementBase {
  static get is() {
    return 'settings-gesture-chips';
  }

  static get template() {
    return html`${CHIP_STYLE}
      <template is="dom-repeat" items="[[getChains_(value, gestures_)]]"
          as="chain">
        <span class="shortcut-chip" title="$i18n{shortcutsGestureLabel}">
          <span class="shortcut-label">[[getLabel_(chain)]]</span>
          <cr-icon-button class="icon-clear" title="$i18n{remove}"
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

// The "Add gesture" button of one command, and its dialog.
export class SettingsAddGestureElement extends PolymerElement {
  static get is() {
    return 'settings-add-gesture';
  }

  static get template() {
    return html`${CHIP_STYLE}
      <template is="dom-if" if="[[enabled_]]">
        <cr-button on-click="onAddClick_">$i18n{shortcutsAddGesture}</cr-button>
      </template>
      <template is="dom-if" if="[[showDialog_]]" restamp>
        <cr-dialog id="gestureDialog" show-on-attach on-close="onClose_">
          <div slot="title">$i18n{shortcutsAddGestureDialogTitle}</div>
          <div slot="body">
            <select class="md-select" aria-label="$i18n{shortcutsGestureLabel}"
                on-change="onTypeChange_">
              <template is="dom-repeat" items="[[types_]]" as="type">
                <option value="[[type]]">[[getLabel_(type)]]</option>
              </template>
            </select>
            <template is="dom-if" if="[[isStroke_(type_)]]">
              <div id="gestureDescription" class="secondary">
                $i18n{shortcutsGestureDescription}
              </div>
              <cr-input id="gestureInput" label="$i18n{shortcutsGestureLabel}"
                  value="{{chain_}}" invalid="[[isInvalid_(chain_)]]"
                  spellcheck="false" autofocus>
              </cr-input>
            </template>
            <template is="dom-if" if="[[message_]]">
              <div class="warning">[[message_]]</div>
            </template>
          </div>
          <div slot="button-container">
            <cr-button class="cancel-button" on-click="onCancelClick_">
              $i18n{cancel}
            </cr-button>
            <cr-button class="action-button"
                disabled="[[!canSave_(type_, chain_)]]"
                on-click="onSaveClick_">
              $i18n{save}
            </cr-button>
          </div>
        </cr-dialog>
      </template>`;
  }

  static get properties() {
    return {
      value: Object,
      name: String,
      enabled_: {
        type: Boolean,
        value: () => mouseGesturesEnabled(),
      },
      showDialog_: {
        type: Boolean,
        value: false,
      },
      chain_: {
        type: String,
        value: '',
        observer: 'updateMessage_',
      },
      type_: {
        type: String,
        value: STROKE,
        observer: 'updateMessage_',
      },
      types_: {
        type: Array,
        value: () => [STROKE, ...Object.keys(GESTURE_LABELS)],
      },
      message_: {
        type: String,
        value: '',
      },
    };
  }

  declare value: GestureValue;
  declare name: string;
  declare private enabled_: boolean;
  declare private showDialog_: boolean;
  declare private chain_: string;
  declare private type_: string;
  declare private types_: string[];
  declare private message_: string;
  private handler_: BrowserShortcutsHandlerRemote|null = null;
  private messageRequestId_ = 0;

  private onAddClick_() {
    this.chain_ = '';
    this.type_ = STROKE;
    this.showDialog_ = true;
  }

  private getLabel_(type: string): string {
    return getGestureLabel(type);
  }

  private isStroke_(type: string): boolean {
    return type === STROKE;
  }

  private onTypeChange_(e: Event) {
    this.type_ = (e.target as HTMLSelectElement).value;
  }

  private getKey_(type: string, chain: string): string|null {
    return type === STROKE ? normalizeGesture(chain) : type;
  }

  private isInvalid_(chain: string): boolean {
    return !!chain && normalizeGesture(chain) === null;
  }

  private canSave_(type: string, chain: string): boolean {
    return this.getKey_(type, chain) !== null;
  }

  // Names the command a gesture is about to be taken from, if any.
  private async updateMessage_() {
    const requestId = ++this.messageRequestId_;
    const key = this.getKey_(this.type_, this.chain_);
    const existing = key === null ? undefined : currentGestures[key];
    if (existing === undefined || isSameGestureValue(existing, this.value)) {
      this.message_ = '';
      return;
    }
    this.handler_ ??= newHandler();
    const name = typeof existing === 'number' ?
        (await this.handler_.getCommands())
            .commands.find(c => c.commandId === existing)
            ?.name :
        (await this.handler_.getExtensionCommands())
            .commands.find(c => isSameGestureValue(toGestureValue(c), existing))
            ?.name;
    if (requestId === this.messageRequestId_) {
      this.message_ =
          name ? loadTimeData.getStringF('shortcutsWillOverride', name) : '';
    }
  }

  private onSaveClick_() {
    const key = this.getKey_(this.type_, this.chain_);
    if (key !== null) {
      PrefService.getInstance().setPrefDictEntry(GESTURES_PREF, key, this.value);
    }
    this.showDialog_ = false;
  }

  private onCancelClick_() {
    this.showDialog_ = false;
  }

  private onClose_() {
    this.showDialog_ = false;
  }
}

// The extension commands, each with its gestures, filtered by the page's
// search.
export class SettingsExtensionGesturesElement extends PolymerElement {
  static get is() {
    return 'settings-extension-gestures';
  }

  static get template() {
    return html`
      <style include="cr-shared-style settings-shared">
        .command-row {
          align-items: center;
          gap: 16px;
          min-height: var(--cr-section-two-line-min-height);
        }

        .command-details {
          flex: 1;
          min-width: 0;
          padding-bottom: var(--cr-section-vertical-padding);
          padding-top: var(--cr-section-vertical-padding);
        }

        .command-name {
          line-height: 20px;
        }

        .shortcut-list {
          align-items: center;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 6px;
        }

        .actions {
          align-items: center;
          display: flex;
          flex-shrink: 0;
          gap: 8px;
        }
      </style>
      <template is="dom-if" if="[[filtered_.length]]">
        <h2 class="cr-title-text">$i18n{shortcutsExtensionCommands}</h2>
        <template is="dom-repeat" items="[[filtered_]]" as="command">
          <div class="cr-row command-row">
            <div class="command-details cr-padded-text">
              <div class="command-name">[[command.name]]</div>
              <div class="shortcut-list secondary">
                <settings-gesture-chips value="[[toValue_(command)]]"
                    name="[[command.name]]">
                </settings-gesture-chips>
              </div>
            </div>
            <div class="separator"></div>
            <div class="actions">
              <settings-add-gesture value="[[toValue_(command)]]"
                  name="[[command.name]]">
              </settings-add-gesture>
            </div>
          </div>
        </template>
      </template>`;
  }

  static get properties() {
    return {
      searchTerm: {
        type: String,
        value: '',
      },
      commands_: {
        type: Array,
        value: () => [],
      },
      filtered_: {
        type: Array,
        computed: 'filter_(commands_, searchTerm)',
      },
    };
  }

  declare searchTerm: string;
  declare private commands_: ExtensionCommand[];
  declare private filtered_: ExtensionCommand[];

  override connectedCallback() {
    super.connectedCallback();
    if (mouseGesturesEnabled()) {
      newHandler().getExtensionCommands().then(({commands}) => {
        this.commands_ = commands.sort((a, b) => a.name.localeCompare(b.name));
      });
    }
  }

  private toValue_(command: ExtensionCommand): GestureValue {
    return toGestureValue(command);
  }

  private filter_(commands: ExtensionCommand[], searchTerm: string):
      ExtensionCommand[] {
    const normalize = (text: string) =>
        text.trim().toLocaleLowerCase().replace(/\s+/g, '');
    const query = normalize(searchTerm);
    return commands.filter(
        command =>
            [command.name,
             ...gesturesFor(toGestureValue(command), currentGestures)
                 .map(getGestureLabel),
    ].some(field => normalize(field).includes(query)));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-gesture-chips': SettingsGestureChipsElement;
    'settings-add-gesture': SettingsAddGestureElement;
    'settings-extension-gestures': SettingsExtensionGesturesElement;
  }
}

customElements.define(SettingsGestureChipsElement.is, SettingsGestureChipsElement);
customElements.define(SettingsAddGestureElement.is, SettingsAddGestureElement);
customElements.define(
    SettingsExtensionGesturesElement.is, SettingsExtensionGesturesElement);
