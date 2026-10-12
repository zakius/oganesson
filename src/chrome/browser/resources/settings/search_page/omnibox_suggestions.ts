// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// The Manage search engines page's "Address bar suggestions" switches and
// suggestion order: which sources the address bar suggests from, and in which
// order. components/omnibox/browser/suggestion_sources.h applies them. A group
// whose switch is off keeps its place in the order, greyed out.
// While browsing history isn't saved (history.saving_disabled), the two
// switches whose suggestions come from history show off and greyed out; their
// prefs keep the user's choice for when it is saved again.

import 'chrome://resources/cr_elements/cr_icon_button/cr_icon_button.js';
import '../controls/settings_toggle_button.js';

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {PrefServiceObserverMixinLit} from '/shared/settings/prefs2/pref_service_observer_mixin_lit.js';
import {I18nMixinLit} from 'chrome://resources/cr_elements/i18n_mixin_lit.js';
import {CrLitElement, css} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss as getSettingsSharedCss} from '../settings_shared_lit.css.js';

import {getHtml} from './omnibox_suggestions.html.js';

export const ORDER_PREF = 'oganesson.omnibox.suggestion_order';
// The groups, in their default order, and the switch that turns each off.
const GROUPS: Record<string, string> = {
  bookmarks: 'oganesson.omnibox.suggest_bookmarks',
  history: 'oganesson.omnibox.suggest_history',
  open_tabs: 'oganesson.omnibox.suggest_open_tabs',
  searches: '',
};
const LABELS: Record<string, string> = {
  bookmarks: 'omniboxSuggestBookmarks',
  history: 'omniboxSuggestHistory',
  open_tabs: 'omniboxSuggestOpenTabs',
  searches: 'omniboxSearches',
};

const SettingsOmniboxSuggestionsElementBase =
    PrefServiceObserverMixinLit(I18nMixinLit(CrLitElement));

export class SettingsOmniboxSuggestionsElement extends
    SettingsOmniboxSuggestionsElementBase {
  static get is() {
    return 'settings-omnibox-suggestions';
  }

  static override get styles() {
    return [
      getSettingsSharedCss(),
      css`
        .list-item.off .label {
          color: var(--cr-secondary-text-color);
        }
      `,
    ];
  }

  override render() {
    return getHtml.bind(this)();
  }

  static override get properties() {
    return {
      historyNotSaved_: {type: Boolean},
      offPref_: {type: Object},
      order_: {type: Array},
      off_: {type: Object},
    };
  }

  protected accessor historyNotSaved_: boolean = false;

  // The pref a switch shows while history isn't saved: off, and never set.
  protected accessor offPref_: chrome.settingsPrivate.PrefObject<boolean> = {
    key: '',
    type: chrome.settingsPrivate.PrefType.BOOLEAN,
    value: false,
  };

  // The group names in the order the pref has, as the browser reads it:
  // names it doesn't know dropped, missing groups after the others.
  protected accessor order_: string[] = Object.keys(GROUPS);
  // The groups whose switch is off.
  protected accessor off_: Record<string, boolean> = {};

  override connectedCallback() {
    super.connectedCallback();
    this.addPrefObserver<boolean>('history.saving_disabled', pref => {
      this.historyNotSaved_ = pref.value;
    });
    this.addPrefObserver<string[]>(ORDER_PREF, pref => {
      const known = pref.value.filter(
          (group, i) => group in GROUPS && pref.value.indexOf(group) === i);
      this.order_ = [
        ...known,
        ...Object.keys(GROUPS).filter(group => !known.includes(group)),
      ];
    });
    for (const [group, key] of Object.entries(GROUPS)) {
      if (key) {
        this.addPrefObserver<boolean>(key, pref => {
          this.off_ = {...this.off_, [group]: !pref.value};
        });
      }
    }
  }

  protected isOff_(group: string): boolean {
    return this.off_[group] === true || (group === 'history' && this.historyNotSaved_);
  }

  protected label_(group: string): string {
    return this.i18n(LABELS[group]);
  }

  protected async onMoveClick_(e: Event) {
    const button = e.currentTarget as HTMLElement;
    const index = Number(button.dataset['index']);
    const to = index + Number(button.dataset['step']);
    const order = [...this.order_];
    const group = order[index];
    order.splice(index, 1);
    order.splice(to, 0, group);
    this.order_ = order;
    PrefService.getInstance().setPrefValue(ORDER_PREF, order);
    // Keyboard focus follows the moved group; at the top or bottom of the
    // list, to its other button.
    await this.updateComplete;
    const last = order.length - 1;
    const up = button.dataset['step'] === '-1' ? to > 0 : to === last;
    this.shadowRoot.querySelector<HTMLElement>(
        `#${group}-${up ? 'up' : 'down'}`)!.focus();
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'settings-omnibox-suggestions': SettingsOmniboxSuggestionsElement;
  }
}

customElements.define(
    SettingsOmniboxSuggestionsElement.is, SettingsOmniboxSuggestionsElement);
