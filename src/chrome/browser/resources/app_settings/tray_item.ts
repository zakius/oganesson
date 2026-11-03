// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import './toggle_row.js';

import type {App} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {browserProxyFactory} from 'chrome://resources/cr_components/app_management/app_management.mojom-webui.js';
import {CrLitElement} from 'chrome://resources/lit/v3_0/lit.rollup.js';
import type {PropertyValues} from 'chrome://resources/lit/v3_0/lit.rollup.js';

import {getCss} from './app_management_shared_style.css.js';
import type {ToggleRowElement} from './toggle_row.js';
import {getHtml} from './tray_item.html.js';
import {createDummyApp} from './web_app_settings_utils.js';

// Whether the app keeps running in the tray when its window closes.
export class TrayItemElement extends CrLitElement {
  static get is() {
    return 'app-management-tray-item';
  }

  static override get styles() {
    return getCss();
  }

  override render() {
    return getHtml.bind(this)();
  }

  static override get properties() {
    return {
      app: {type: Object},
      enabled_: {type: Boolean},
    };
  }

  accessor app: App = createDummyApp();
  protected accessor enabled_: boolean = false;

  override willUpdate(changedProperties: PropertyValues<this>) {
    super.willUpdate(changedProperties);
    const previous = changedProperties.get('app');
    if (changedProperties.has('app') && this.app.id &&
        previous?.id !== this.app.id) {
      browserProxyFactory.getInstance().handler.getTrayApp(this.app.id)
          .then(({enabled}) => {
            this.enabled_ = enabled;
          });
    }
  }

  override firstUpdated() {
    this.addEventListener('click', () => {
      this.shadowRoot.querySelector<ToggleRowElement>('#toggle-row')!.click();
    });
    this.addEventListener('change', () => {
      this.enabled_ = !this.enabled_;
      browserProxyFactory.getInstance().handler.setTrayApp(
          this.app.id, this.enabled_);
    });
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-management-tray-item': TrayItemElement;
  }
}

customElements.define(TrayItemElement.is, TrayItemElement);
