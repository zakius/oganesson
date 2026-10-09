// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_dialog/cr_dialog.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '../settings_shared.css.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import type {BrowserShortcutsHandlerRemote} from '../browser_shortcuts.mojom-webui.js';
import {loadTimeData} from '../i18n_setup.js';

import type {GestureValue} from './mouse_gestures.js';
import {CHIP_STYLE, getCurrentGestures, getGestureLabel, GESTURE_LABELS, GESTURES_PREF, isSameGestureValue, mouseGesturesEnabled, newHandler, normalizeGesture, STROKE, toGestureValue} from './mouse_gestures.js';

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
    const existing = key === null ? undefined : getCurrentGestures()[key];
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

declare global {
  interface HTMLElementTagNameMap {
    'settings-add-gesture': SettingsAddGestureElement;
  }
}

customElements.define(SettingsAddGestureElement.is, SettingsAddGestureElement);
