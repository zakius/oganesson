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
<cr-checkbox id="strict" ?checked="${this.strict_}"
    @change="${this.onStrictChange_}">
  Send every page outside the app to the default browser
</cr-checkbox>
<ul id="strictConsequences" class="secondary-text">
  <li>
    Pages outside the app go to the default browser however the app gets
    there: by script, by redirect, or in a popup, not only when you click a
    link.
  </li>
  <li>
    Signing in within the app stops working where it goes through another
    site or a popup, as "Continue with Google" does. Sign in in the default
    browser, then open the app.
  </li>
  <li>
    Payment and verification steps on another site open in the default
    browser and may not return to the app.
  </li>
  <li>
    The default browser uses its own sign-ins, not the app's, unless it is
    this browser.
  </li>
  <li>Form posts and back and forward still stay in the app.</li>
</ul>
<div id="actions">
  <cr-button id="save" @click="${this.onSaveClick_}">
    ${this.saved_ ? 'Saved' : 'Save'}
  </cr-button>
</div>
<!--_html_template_end_-->`;
  // clang-format on
}
