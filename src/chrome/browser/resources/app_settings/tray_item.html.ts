// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

import {html} from '//resources/lit/v3_0/lit.rollup.js';

import type {TrayItemElement} from './tray_item.js';

export function getHtml(this: TrayItemElement) {
  return html`<!--_html_template_start_-->
<app-management-toggle-row id="toggle-row" label="Keep running in the tray"
    description="Closing the app's window hides it in the system tray, where its icon brings it back. The app keeps getting notifications with every other window closed. It starts there at login."
    ?value="${this.enabled_}">
</app-management-toggle-row>
<!--_html_template_end_-->`;
}
