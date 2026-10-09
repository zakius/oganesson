// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Mouse gestures on the "Shortcuts and gestures" page: what the elements in
// gesture_chips.ts, add_gesture.ts and extension_gestures.ts share. The page
// places them in its command rows and after the commands; they keep their
// own state, so Helium's page only hosts them.

import {PrefService} from '/shared/settings/prefs2/pref_service.js';
import {html} from 'chrome://resources/polymer/v3_0/polymer/polymer_bundled.min.js';

import {BrowserShortcutsHandlerFactory, BrowserShortcutsHandlerRemote, BrowserShortcutsPageCallbackRouter} from '../browser_shortcuts.mojom-webui.js';
import type {ExtensionCommand} from '../browser_shortcuts.mojom-webui.js';
import {loadTimeData} from '../i18n_setup.js';

// Maps mouse gestures to a GestureValue. Keys are stroke chains, such as "DR",
// or one of the non-stroke gestures below.
export const GESTURES_PREF = 'oganesson.mouse_gestures';
export const STROKE = 'stroke';

// A browser command id, or an extension command.
export type GestureValue = number|{extension: string, command: string};

export const GESTURE_LABELS: Record<string, string> = {
  'rocker-rl': 'shortcutsGestureRockerRightLeft',
  'rocker-lr': 'shortcutsGestureRockerLeftRight',
  'wheel-up': 'shortcutsGestureWheelUp',
  'wheel-down': 'shortcutsGestureWheelDown',
};

export function isSameGestureValue(a: GestureValue, b: GestureValue): boolean {
  return typeof a === 'number' || typeof b === 'number' ?
      a === b :
      a.extension === b.extension && a.command === b.command;
}

export function toGestureValue(command: ExtensionCommand): GestureValue {
  return {extension: command.extensionId, command: command.commandName};
}

// The recognizer collapses repeated directions, so "LL" can never match.
export function normalizeGesture(chain: string): string|null {
  const normalized = chain.trim().toUpperCase();
  return /^[LRUD]{1,64}$/.test(normalized) && !/(.)\1/.test(normalized) ?
      normalized :
      null;
}

export function getGestureLabel(gesture: string): string {
  if (gesture === STROKE) {
    return loadTimeData.getString('shortcutsGestureStroke');
  }
  const label = GESTURE_LABELS[gesture];
  return label ? loadTimeData.getString(label) : gesture;
}

export function gesturesFor(
    value: GestureValue|null, gestures: Record<string, GestureValue>):
    string[] {
  return value === null ?
      [] :
      Object.keys(gestures)
          .filter(chain => isSameGestureValue(gestures[chain], value))
          .sort();
}

export function newHandler(): BrowserShortcutsHandlerRemote {
  const handler = new BrowserShortcutsHandlerRemote();
  BrowserShortcutsHandlerFactory.getRemote().createBrowserShortcutsHandler(
      new BrowserShortcutsPageCallbackRouter().$.bindNewPipeAndPassRemote(),
      handler.$.bindNewPipeAndPassReceiver());
  return handler;
}

export function mouseGesturesEnabled(): boolean {
  return loadTimeData.getBoolean('showMouseGestures');
}

// The gestures last seen, for the page's search, which ranks a command by its
// gesture labels too.
let currentGestures: Record<string, GestureValue> = {};
PrefService.getInstance().addObserver<Record<string, GestureValue>>(
    GESTURES_PREF, pref => currentGestures = pref.value);

// The gestures last seen.
export function getCurrentGestures(): Record<string, GestureValue> {
  return currentGestures;
}

export function gestureSearchFields(commandId: number): string[] {
  return gesturesFor(commandId, currentGestures).map(getGestureLabel);
}

export const CHIP_STYLE = html`
  <style include="cr-shared-style settings-shared md-select">
    :host {
      display: contents;
    }

    .shortcut-chip {
      align-items: center;
      background: var(--cr-hover-background-color);
      border: 1px solid transparent;
      border-radius: 8px;
      color: var(--cr-primary-text-color);
      display: inline-flex;
      font-size: 12px;
      font-weight: 500;
      line-height: 20px;
      min-height: 28px;
      overflow: hidden;
      padding-inline-end: 2px;
      padding-inline-start: 10px;
      white-space: nowrap;
    }

    .shortcut-label {
      align-items: center;
      display: inline-flex;
      height: 24px;
      line-height: 24px;
    }

    .shortcut-chip cr-icon-button {
      --cr-icon-button-icon-size: 16px;
      --cr-icon-button-margin-end: 0;
      --cr-icon-button-margin-start: 0;
      --cr-icon-button-size: 24px;
      flex-shrink: 0;
      margin-inline-start: 4px;
    }

    cr-button {
      --cr-button-height: 32px;
    }

    #gestureDescription,
    #gestureInput {
      margin-top: 12px;
    }

    .warning {
      color: var(--google-red-700);
      margin-top: 12px;
    }
  </style>`;
