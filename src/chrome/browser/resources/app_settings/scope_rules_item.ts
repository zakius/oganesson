// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import '//resources/cr_elements/cr_button/cr_button.js';
import '//resources/cr_elements/cr_textarea/cr_textarea.js';

import type {App} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {browserProxyFactory} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {CrLitElement, css} from 'chrome://resources/lit/v3_0/lit.rollup.js';
import type {PropertyValues} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss} from './app_management_shared_style.css.js';
import {getHtml} from './scope_rules_item.html.js';
import {createDummyApp} from './web_app_settings_utils.js';

// The URL patterns the user adds to the app's scope.
export class ScopeRulesItemElement extends CrLitElement {
  static get is() {
    return 'app-management-scope-rules-item';
  }

  static override get styles() {
    // cr-textarea hides its footer, where the error shows, unless told not to.
    return [getCss(), css`
      p {
        margin: 0 0 8px;
      }
      cr-textarea {
        --cr-textarea-footer-display: flex;
        font-family: monospace;
      }
      #actions {
        display: flex;
        justify-content: flex-end;
        padding-block-end: 12px;
      }
    `];
  }

  override render() {
    return getHtml.bind(this)();
  }

  static override get properties() {
    return {
      app: {type: Object},
      rules_: {type: String},
      error_: {type: String},
      saved_: {type: Boolean},
    };
  }

  accessor app: App = createDummyApp();
  protected accessor rules_: string = '';
  protected accessor error_: string = '';
  protected accessor saved_: boolean = false;

  override willUpdate(changedProperties: PropertyValues<this>) {
    super.willUpdate(changedProperties);
    const previous = changedProperties.get('app');
    if (changedProperties.has('app') && this.app.id &&
        previous?.id !== this.app.id) {
      browserProxyFactory.getInstance().handler.getScopeRules(this.app.id)
          .then(({rules}) => this.rules_ = rules);
    }
  }

  protected onRulesValueChanged_(e: CustomEvent<{value: string}>) {
    this.rules_ = e.detail.value;
    this.saved_ = false;
  }

  protected async onSaveClick_() {
    const {error} =
        await browserProxyFactory.getInstance().handler.setScopeRules(
            this.app.id, this.rules_);
    this.error_ = error;
    this.saved_ = !error;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-management-scope-rules-item': ScopeRulesItemElement;
  }
}

customElements.define(ScopeRulesItemElement.is, ScopeRulesItemElement);
