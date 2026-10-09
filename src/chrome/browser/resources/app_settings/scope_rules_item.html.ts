// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {html} from '//resources/lit/v3_0/lit.rollup.js';

import type {ScopeRulesItemElement} from './scope_rules_item.js';

export function getHtml(this: ScopeRulesItemElement) {
  // clang-format off
  return html`<!--_html_template_start_-->
<div class="permission-section-header header-text">Pages that stay in the app</div>
<p class="secondary-text">
  URL patterns added to the app's scope, one per line, such as
  https://*.example.com/*. A rule naming a site the app is on replaces the
  app's scope there: https://example.com/mail/* keeps only those pages of
  example.com in the app. A pattern starting with ! takes the pages it
  matches out of the app.
</p>
<cr-textarea id="rules" .value="${this.rules_}" ?invalid="${!!this.error_}"
    first-footer="${this.error_}" @value-changed="${this.onRulesValueChanged_}"
    rows="4" autogrow>
</cr-textarea>
<div id="actions">
  <cr-button id="save" @click="${this.onSaveClick_}">
    ${this.saved_ ? 'Saved' : 'Save'}
  </cr-button>
</div>
<!--_html_template_end_-->`;
  // clang-format on
}
