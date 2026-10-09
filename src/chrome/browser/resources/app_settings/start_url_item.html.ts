// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {html} from '//resources/lit/v3_0/lit.rollup.js';

import type {StartUrlItemElement} from './start_url_item.js';

export function getHtml(this: StartUrlItemElement) {
  // clang-format off
  return html`<!--_html_template_start_-->
<div class="permission-section-header header-text">Start address</div>
<p class="secondary-text">
  The page the app opens at, from the app list, its menu or its desktop
  entry. Leave it empty for the app's own, shown greyed in the field.
</p>
<cr-input id="url" type="url" .value="${this.url_}"
    placeholder="${this.manifestStartUrl_}" ?invalid="${!!this.error_}"
    error-message="${this.error_}" @value-changed="${this.onUrlValueChanged_}">
</cr-input>
<div id="actions">
  <cr-button id="save" @click="${this.onSaveClick_}">
    ${this.saved_ ? 'Saved' : 'Save'}
  </cr-button>
</div>
<!--_html_template_end_-->`;
  // clang-format on
}
