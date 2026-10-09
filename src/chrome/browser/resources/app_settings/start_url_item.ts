// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import '//resources/cr_elements/cr_button/cr_button.js';
import '//resources/cr_elements/cr_input/cr_input.js';

import type {App} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {browserProxyFactory} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {CrLitElement, css} from 'chrome://resources/lit/v3_0/lit.rollup.js';
import type {PropertyValues} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss} from './app_management_shared_style.css.js';
import {getHtml} from './start_url_item.html.js';
import {createDummyApp} from './web_app_settings_utils.js';

// The URL the user sets for the app to open at (#346).
export class StartUrlItemElement extends CrLitElement {
  static get is() {
    return 'app-management-start-url-item';
  }

  static override get styles() {
    return [getCss(), css`
      p {
        margin: 0 0 8px;
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
      url_: {type: String},
      manifestStartUrl_: {type: String},
      error_: {type: String},
      saved_: {type: Boolean},
    };
  }

  accessor app: App = createDummyApp();
  protected accessor url_: string = '';
  protected accessor manifestStartUrl_: string = '';
  protected accessor error_: string = '';
  protected accessor saved_: boolean = false;

  override willUpdate(changedProperties: PropertyValues<this>) {
    super.willUpdate(changedProperties);
    const previous = changedProperties.get('app');
    if (changedProperties.has('app') && this.app.id &&
        previous?.id !== this.app.id) {
      browserProxyFactory.getInstance().handler.getStartUrl(this.app.id)
          .then(({url, manifestStartUrl}) => {
            this.url_ = url;
            this.manifestStartUrl_ = manifestStartUrl;
          });
    }
  }

  protected onUrlValueChanged_(e: CustomEvent<{value: string}>) {
    this.url_ = e.detail.value;
    this.saved_ = false;
  }

  protected async onSaveClick_() {
    const {error} =
        await browserProxyFactory.getInstance().handler.setStartUrl(
            this.app.id, this.url_);
    this.error_ = error;
    this.saved_ = !error;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-management-start-url-item': StartUrlItemElement;
  }
}

customElements.define(StartUrlItemElement.is, StartUrlItemElement);
