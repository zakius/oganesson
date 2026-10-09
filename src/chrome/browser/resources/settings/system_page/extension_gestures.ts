// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

import './add_gesture.js';
import './gesture_chips.js';
import '../settings_shared.css.js';

import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import type {ExtensionCommand} from '../browser_shortcuts.mojom-webui.js';

import type {GestureValue} from './mouse_gestures.js';
import {getCurrentGestures, getGestureLabel, gesturesFor, mouseGesturesEnabled, newHandler, toGestureValue} from './mouse_gestures.js';

// The extension commands, each with its gestures, filtered by the page's
// search.
const SettingsExtensionGesturesElementBase = I18nMixin(PolymerElement);

export class SettingsExtensionGesturesElement extends SettingsExtensionGesturesElementBase {
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
        <h2 class="cr-title-text">[[i18n('shortcutsExtensionCommands')]]</h2>
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
             ...gesturesFor(toGestureValue(command), getCurrentGestures())
                 .map(getGestureLabel),
    ].some(field => normalize(field).includes(query)));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-extension-gestures': SettingsExtensionGesturesElement;
  }
}

customElements.define(SettingsExtensionGesturesElement.is, SettingsExtensionGesturesElement);
