# Translation

Page translation is an opt-in, off by default. Settings > Languages > Translation has a "Translate pages" switch and two engines:

- **On this device** (the default engine): Chromium's TranslateKit translates in the browser. The engine and its language packs download from Google's component updater; page text stays on the device.
- **With Google Translate**: the page text goes to Google Translate's keyless endpoint. More languages, nothing to download.

Once it is on, the page context menu has "Translate to <language>" and the address bar shows Helium's translate button, the app menu has Translate, and the rest of Chromium's Translation settings show (offering to translate, the target language, always and never lists). While it is off, the browser sends and downloads nothing for translation, and pages can't use the web `Translator` API.

The setting is in Local State, one for the whole browser, like Browser traffic: Helium's translation providers are global. The setup's Google features step (zakius/oganesson#97) is to offer the same switch.

## How it fits in

Helium 0.21.3.1 added its own translation chain, behind the `HeliumTranslate` feature: a page script that walks the page and sends its text in batches to the browser (`helium/core/translate/*`), where a registered `TranslationProvider` translates it, and the UI that shows only when a provider is registered (`helium/ui/translate-ui`). Helium registers no provider. `oganesson/core/translation` turns the feature on and registers two (`src/chrome/browser/translate/oganesson_translation_providers.cc`), each available only while the setting picks it. With neither available, Helium's code falls back to Chromium's, which needs an API key we don't have, so nothing is offered.

oganesson-core (snapshot `f0b3941`) had its own 1,100-line chain on Chromium's Google Translate Element. Helium's chain replaces most of it: what is ours is the two providers, the setting, the download question and the component updater gate.

### On this device

The provider runs Chromium's on-device translation service, as the `Translator` API does, with one service for every page. Each text run goes to TranslateKit on its own. TranslateKit doesn't detect languages, so a page whose language is unknown can't be translated on the device.

- TranslateKit's language packs each pair English with one other language. A translation between two other languages goes through English and needs both packs.
- Before a translation that needs a pack that isn't installed, the browser asks: "Download languages for translation?", naming the languages. With a yes, the packs (and the engine, the first time) download, and the page translates once they are in. With Cancel, nothing downloads.
- Helium's `component-updates` lets only an allowlist of components register. TranslateKit's components, the engine and the packs, are the exception (`src/components/component_updater/translate_kit_gate.h`). Chromium registers them when on-device translation first needs them. They check for updates at Google's update server, on demand and with the automatic checks, only while on-device translation is on: once it is off, installed packs stay and nothing asks for their updates. They are not a Browser traffic row: they have no proxy route, and the translation setting is their switch.
- Pages can use the `Translator` API only while on-device translation is on. Otherwise a page could make the browser download TranslateKit.

### With Google Translate

The provider posts each batch's text to `translate.googleapis.com/translate_a/t?client=gtx`, the keyless endpoint Google's own website widget and many browser add-ons use, without cookies. The reply lists one translation per text, and the detected language when the page's language is unknown.

## Tests

`tools/e2e/test_translation.py`, offline: Google's hosts go to local stand-ins with `--host-resolver-rules`.

- Off by default: no menu item, no `Translator` API, no request to a translate host, and no TranslateKit update check.
- The switch and the engine choice in Settings.
- Google Translate: the page text reaches the stand-in endpoint and its reply replaces it.
- On this device: Chromium's stand-in TranslateKit library (`mock_translate_kit_lib`, which `linux/container-build.sh` builds next to the browser and the packages leave out) with a pack given on the command line translates the page.
- The download question: a cancel checks for nothing; a yes makes the component updater ask the update server for TranslateKit and the German pack.

## What it depends on

Undocumented Google behaviour: if Google stops serving the keyless endpoint, or TranslateKit through the component updater, that engine stops working. The tests use stand-ins, so they don't notice: a manual check with the real servers does.
