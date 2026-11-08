// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Settings > Privacy and security > Containers: the user's containers and
// Traffic Control's rules. Both are list prefs (dubna's
// chrome/browser/containers/container.h), which this page edits; the browser
// does the rest, such as closing a deleted container's tabs and deleting its
// storage. Icons and colors come from the browser (containers_desktop.cc).

import 'chrome://resources/cr_elements/cr_button/cr_button.js';
import 'chrome://resources/cr_elements/cr_dialog/cr_dialog.js';
import 'chrome://resources/cr_elements/cr_icon_button/cr_icon_button.js';
import 'chrome://resources/cr_elements/cr_input/cr_input.js';
import 'chrome://resources/cr_elements/cr_textarea/cr_textarea.js';
import 'chrome://resources/cr_elements/cr_toggle/cr_toggle.js';
import 'chrome://resources/cr_elements/icons.html.js';
import 'chrome://resources/cr_elements/md_select.css.js';
import '../settings_page/settings_subpage.js';
import '../settings_shared.css.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {PrefServiceObserverMixin} from '/shared/settings/prefs2/pref_service_observer_mixin.js';
import {I18nMixin} from 'chrome://resources/cr_elements/i18n_mixin.js';
import {html, PolymerElement} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {loadTimeData} from '../i18n_setup.js';

interface Container {
  id: string;
  name: string;
  icon: string;
  color: string;
}

interface TrafficRule {
  url_filter: string;
  container: string;
  enabled: boolean;
}

type ContainerEvent = Event&{model: {item: Container}};
type RuleEvent = Event&{model: {item: TrafficRule, index: number}};
type ChoiceEvent = Event&{model: {item: string}};

const CONTAINERS_PREF = 'containers.list';
const RULES_PREF = 'containers.traffic_control';
// A rule's container that is a new temporary one each time.
const TEMPORARY = 'temporary';

function iconUrl(icon: string): string {
  const key = 'containerIcon_' + icon;
  return loadTimeData.valueExists(key) ? loadTimeData.getString(key) :
                                         loadTimeData.getString('containerIcon_circle');
}

function colorValue(color: string): string {
  const key = 'containerColor_' + color;
  return loadTimeData.valueExists(key) ? loadTimeData.getString(key) :
                                         loadTimeData.getString('containerColor_toolbar');
}

// The style of an element that shows `icon` in `color`.
function iconStyle(icon: string, color: string): string {
  return `-webkit-mask-image: url("${iconUrl(icon)}"); ` +
      `background-color: ${colorValue(color)};`;
}

// The lines of a rule's sites that are patterns.
function patterns(urlFilter: string): string[] {
  return urlFilter.split('\n').map(line => line.trim())
      .filter(line => line && !line.startsWith('#'));
}

const SettingsContainersPageElementBase =
    I18nMixin(PrefServiceObserverMixin(PolymerElement));

export class SettingsContainersPageElement extends
    SettingsContainersPageElementBase {
  static get is() {
    return 'settings-containers-page';
  }

  static get template() {
    return html`
      <style include="cr-shared-style settings-shared md-select">
        .container-icon {
          -webkit-mask-position: center;
          -webkit-mask-repeat: no-repeat;
          -webkit-mask-size: contain;
          display: inline-block;
          flex-shrink: 0;
          height: 20px;
          margin-inline-end: 16px;
          width: 20px;
        }
        .choices {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 16px;
        }
        .choice {
          align-items: center;
          background: none;
          border: 2px solid transparent;
          border-radius: 50%;
          cursor: pointer;
          display: flex;
          height: 32px;
          justify-content: center;
          padding: 0;
          width: 32px;
        }
        .choice[aria-pressed=true] {
          border-color: var(--cr-checked-color);
        }
        .swatch {
          border-radius: 50%;
          height: 20px;
          width: 20px;
        }
        .choice .container-icon {
          margin: 0;
        }
        .label {
          color: var(--cr-secondary-text-color);
          display: block;
          margin-bottom: 8px;
        }
        h2 {
          padding-top: 16px;
        }
        .rule-text {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        cr-toggle {
          margin-inline-end: 16px;
        }
        cr-textarea {
          margin-bottom: 16px;
        }
      </style>
      <settings-subpage page-title="[[i18n('containersTitle')]]"
          route-path$="[[routePath]]">
        <div class="cr-row first">
          <div class="flex cr-padded-text secondary">
            [[i18n('containersDescription')]]
          </div>
          <cr-button id="addContainer" on-click="onAddContainerClick_">
            [[i18n('containersAdd')]]
          </cr-button>
        </div>
        <template is="dom-repeat" items="[[containers_]]">
          <div class="cr-row container">
            <span class="container-icon"
                style$="[[iconStyle_(item.icon, item.color)]]"></span>
            <div class="flex">[[item.name]]</div>
            <cr-icon-button class="icon-edit edit"
                title="[[i18n('containersEdit')]]"
                on-click="onEditContainerClick_"></cr-icon-button>
            <cr-icon-button class="icon-delete-gray delete"
                title="[[i18n('delete')]]"
                on-click="onDeleteContainerClick_"></cr-icon-button>
          </div>
        </template>
        <div class="cr-row" hidden="[[containers_.length]]">
          [[i18n('containersNoneYet')]]
        </div>

        <div class="cr-row continuation">
          <h2 class="flex">[[i18n('trafficControlTitle')]]</h2>
        </div>
        <div class="cr-row first">
          <div class="flex cr-padded-text secondary">
            [[i18n('trafficControlDescription')]]
          </div>
          <cr-button id="addRule" on-click="onAddRuleClick_">
            [[i18n('trafficControlAdd')]]
          </cr-button>
        </div>
        <template is="dom-repeat" items="[[rules_]]">
          <div class="cr-row rule">
            <cr-toggle checked="[[item.enabled]]"
                aria-label="[[ruleSites_(item)]]"
                on-change="onRuleToggle_"></cr-toggle>
            <div class="flex rule-text">
              <div class="rule-text">[[ruleSites_(item)]]</div>
              <div class="secondary">[[targetName_(item.container, containers_)]]</div>
            </div>
            <cr-icon-button class="icon-edit edit"
                title="[[i18n('trafficControlEdit')]]"
                on-click="onEditRuleClick_"></cr-icon-button>
            <cr-icon-button class="icon-delete-gray delete"
                title="[[i18n('delete')]]"
                on-click="onDeleteRuleClick_"></cr-icon-button>
          </div>
        </template>
        <div class="cr-row" hidden="[[rules_.length]]">
          [[i18n('trafficControlNoneYet')]]
        </div>
      </settings-subpage>

      <template is="dom-if" if="[[editing_]]" restamp>
        <cr-dialog id="containerDialog" show-on-attach
            on-close="onContainerDialogClose_">
          <div slot="title">[[containerDialogTitle_(editing_)]]</div>
          <div slot="body">
            <cr-input id="name" label="[[i18n('containersName')]]"
                value="{{editing_.name}}" autofocus></cr-input>
            <span class="label">[[i18n('containersColor')]]</span>
            <div class="choices" id="colors">
              <template is="dom-repeat" items="[[colors_]]">
                <button class="choice" aria-label="[[item]]"
                    aria-pressed$="[[isEqual_(item, editing_.color)]]"
                    on-click="onColorClick_">
                  <span class="swatch" style$="[[swatchStyle_(item)]]"></span>
                </button>
              </template>
            </div>
            <span class="label">[[i18n('containersIcon')]]</span>
            <div class="choices" id="icons">
              <template is="dom-repeat" items="[[icons_]]">
                <button class="choice" aria-label="[[item]]"
                    aria-pressed$="[[isEqual_(item, editing_.icon)]]"
                    on-click="onIconClick_">
                  <span class="container-icon"
                      style$="[[iconStyle_(item, editing_.color)]]"></span>
                </button>
              </template>
            </div>
          </div>
          <div slot="button-container">
            <cr-button class="cancel-button" on-click="onCancelClick_">
              [[i18n('cancel')]]
            </cr-button>
            <cr-button class="action-button" id="saveContainer"
                disabled="[[!canSaveContainer_(editing_.name)]]"
                on-click="onSaveContainerClick_">
              [[i18n('save')]]
            </cr-button>
          </div>
        </cr-dialog>
      </template>

      <template is="dom-if" if="[[deleting_]]" restamp>
        <cr-dialog id="deleteDialog" show-on-attach
            on-close="onDeleteDialogClose_">
          <div slot="title">[[deleteTitle_(deleting_)]]</div>
          <div slot="body">[[i18n('containersDeleteBody')]]</div>
          <div slot="button-container">
            <cr-button class="cancel-button" on-click="onCancelClick_">
              [[i18n('cancel')]]
            </cr-button>
            <cr-button class="action-button" id="confirmDelete"
                on-click="onConfirmDeleteClick_">
              [[i18n('delete')]]
            </cr-button>
          </div>
        </cr-dialog>
      </template>

      <template is="dom-if" if="[[editingRule_]]" restamp>
        <cr-dialog id="ruleDialog" show-on-attach on-close="onRuleDialogClose_">
          <div slot="title">[[ruleDialogTitle_(editingRuleIndex_)]]</div>
          <div slot="body">
            <cr-textarea id="sites" label="[[i18n('trafficControlSites')]]"
                value="{{editingRule_.url_filter}}" spellcheck="false"
                invalid="[[isInvalidSites_(editingRule_.url_filter)]]"
                first-footer="[[i18n('trafficControlSitesInvalid')]]"
                autofocus></cr-textarea>
            <span class="label">[[i18n('trafficControlOpenIn')]]</span>
            <select class="md-select" id="target"
                aria-label="[[i18n('trafficControlOpenIn')]]"
                on-change="onTargetChange_">
              <option value="" selected$="[[isEqual_('', editingRule_.container)]]">
                [[i18n('trafficControlNone')]]
              </option>
              <option value="temporary"
                  selected$="[[isEqual_('temporary', editingRule_.container)]]">
                [[i18n('trafficControlTemporary')]]
              </option>
              <template is="dom-repeat" items="[[containers_]]">
                <option value="[[item.id]]"
                    selected$="[[isEqual_(item.id, editingRule_.container)]]">
                  [[item.name]]
                </option>
              </template>
            </select>
          </div>
          <div slot="button-container">
            <cr-button class="cancel-button" on-click="onCancelClick_">
              [[i18n('cancel')]]
            </cr-button>
            <cr-button class="action-button" id="saveRule"
                disabled="[[!hasPatterns_(editingRule_.url_filter)]]"
                on-click="onSaveRuleClick_">
              [[i18n('save')]]
            </cr-button>
          </div>
        </cr-dialog>
      </template>`;
  }

  static get properties() {
    return {
      // Set by privacy_page_index.html, for settings-subpage.
      routePath: String,
      containers_: {type: Array, value: () => []},
      rules_: {type: Array, value: () => []},
      colors_: {
        type: Array,
        value: () => loadTimeData.getString('containerColors').split(','),
      },
      icons_: {
        type: Array,
        value: () => loadTimeData.getString('containerIcons').split(','),
      },
      // The container the dialog edits, a copy; null when it's closed.
      editing_: {type: Object, value: null},
      deleting_: {type: Object, value: null},
      editingRule_: {type: Object, value: null},
      // The rule's index, -1 for a new one.
      editingRuleIndex_: {type: Number, value: -1},
    };
  }

  declare routePath: string;
  declare private containers_: Container[];
  declare private rules_: TrafficRule[];
  declare private colors_: string[];
  declare private icons_: string[];
  declare private editing_: Container|null;
  declare private deleting_: Container|null;
  declare private editingRule_: TrafficRule|null;
  declare private editingRuleIndex_: number;
  // Whether the dialog edits a container of the list, or a new one.
  private editingExisting_ = false;

  override connectedCallback() {
    super.connectedCallback();
    this.addPrefObserver<Container[]>(CONTAINERS_PREF, pref => {
      this.containers_ = (pref.value || []).map(c => ({...c}));
    });
    this.addPrefObserver<TrafficRule[]>(RULES_PREF, pref => {
      this.rules_ = (pref.value || []).map(r => ({...r}));
    });
  }

  private iconStyle_(icon: string, color: string): string {
    return iconStyle(icon, color);
  }

  private swatchStyle_(color: string): string {
    return `background-color: ${colorValue(color)};`;
  }

  private isEqual_(a: string, b: string): boolean {
    return a === b;
  }

  private containerDialogTitle_(): string {
    return this.i18n(this.editingExisting_ ? 'containersEdit' : 'containersAdd');
  }

  private ruleDialogTitle_(index: number): string {
    return this.i18n(index < 0 ? 'trafficControlAdd' : 'trafficControlEdit');
  }

  private deleteTitle_(container: Container): string {
    return loadTimeData.getStringF('containersDeleteTitle', container.name);
  }

  private canSaveContainer_(name: string): boolean {
    return !!name && !!name.trim();
  }

  private hasPatterns_(urlFilter: string): boolean {
    return patterns(urlFilter || '').length > 0;
  }

  private isInvalidSites_(urlFilter: string): boolean {
    return !!urlFilter && !this.hasPatterns_(urlFilter);
  }

  private ruleSites_(rule: TrafficRule): string {
    return patterns(rule.url_filter).join(', ');
  }

  private targetName_(target: string, containers: Container[]): string {
    if (target === '') {
      return this.i18n('trafficControlNone');
    }
    if (target === TEMPORARY) {
      return this.i18n('trafficControlTemporary');
    }
    return containers.find(c => c.id === target)?.name || target;
  }

  private setContainers_(containers: Container[]) {
    PrefService.getInstance().setPrefValue(CONTAINERS_PREF, containers);
  }

  private setRules_(rules: TrafficRule[]) {
    PrefService.getInstance().setPrefValue(RULES_PREF, rules);
  }

  private onAddContainerClick_() {
    this.editingExisting_ = false;
    this.editing_ = {
      id: crypto.randomUUID(),
      name: '',
      icon: this.icons_[0],
      color: this.colors_[0],
    };
  }

  private onEditContainerClick_(e: ContainerEvent) {
    this.editingExisting_ = true;
    this.editing_ = {...e.model.item};
  }

  private onColorClick_(e: ChoiceEvent) {
    this.set('editing_.color', e.model.item);
  }

  private onIconClick_(e: ChoiceEvent) {
    this.set('editing_.icon', e.model.item);
  }

  private onSaveContainerClick_() {
    const container = {...this.editing_!, name: this.editing_!.name.trim()};
    const containers = this.containers_.map(c => ({...c}));
    const index = containers.findIndex(c => c.id === container.id);
    if (index < 0) {
      containers.push(container);
    } else {
      containers[index] = container;
    }
    this.setContainers_(containers);
    this.editing_ = null;
  }

  private onDeleteContainerClick_(e: ContainerEvent) {
    this.deleting_ = e.model.item;
  }

  private onConfirmDeleteClick_() {
    const id = this.deleting_!.id;
    this.setContainers_(this.containers_.filter(c => c.id !== id));
    this.deleting_ = null;
  }

  private onAddRuleClick_() {
    this.editingRuleIndex_ = -1;
    this.editingRule_ = {url_filter: '', container: TEMPORARY, enabled: true};
  }

  private onEditRuleClick_(e: RuleEvent) {
    this.editingRuleIndex_ = e.model.index;
    this.editingRule_ = {...e.model.item};
  }

  private onTargetChange_(e: Event) {
    this.set('editingRule_.container', (e.target as HTMLSelectElement).value);
  }

  private onSaveRuleClick_() {
    const rules = this.rules_.map(r => ({...r}));
    if (this.editingRuleIndex_ < 0) {
      rules.push({...this.editingRule_!});
    } else {
      rules[this.editingRuleIndex_] = {...this.editingRule_!};
    }
    this.setRules_(rules);
    this.editingRule_ = null;
  }

  private onRuleToggle_(e: RuleEvent) {
    const rules = this.rules_.map(r => ({...r}));
    rules[e.model.index].enabled = !rules[e.model.index].enabled;
    this.setRules_(rules);
  }

  private onDeleteRuleClick_(e: RuleEvent) {
    this.setRules_(this.rules_.filter((_, i) => i !== e.model.index));
  }

  private onCancelClick_(e: Event) {
    (e.target as HTMLElement).closest('cr-dialog')!.close();
  }

  private onContainerDialogClose_() {
    this.editing_ = null;
  }

  private onDeleteDialogClose_() {
    this.deleting_ = null;
  }

  private onRuleDialogClose_() {
    this.editingRule_ = null;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-containers-page': SettingsContainersPageElement;
  }
}

customElements.define(
    SettingsContainersPageElement.is, SettingsContainersPageElement);
