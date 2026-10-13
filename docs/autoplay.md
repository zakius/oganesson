# Autoplay

Settings → Privacy and security → Site settings → Autoplay (in "Additional content settings") has Firefox's three choices. It is the `autoplay` content setting (`ContentSettingsType::AUTOPLAY`, a type Chromium registers but no longer uses):

| Choice | Value | What plays without user input |
|---|---|---|
| Allow audio and video | `ALLOW` | Everything. |
| Block audio | `ASK` | Chromium's own policy: muted video, and media with sound once the user interacted with the site, also on a page opened from it, and on sites with high media engagement. As with Block audio and video, an extension's script or message isn't interaction. |
| Block audio and video (default) | `BLOCK` | Nothing, muted media included. |

Exceptions for a site are Allow or Block, set on the Autoplay page or in the site's permissions. The setting of the top-level site applies to all its frames. A changed setting applies to the next page loaded, not to pages already open.

## Block audio and video

A media element, Web Audio (`AudioContext`) and speech synthesis start only after a user activation in the document itself: a click, a key press or a tap in the page. These don't count:

- the activation of the page that opened this one, by a link in the same tab or by a middle click into a new tab, or as its opener;
- switching to the tab or focusing it;
- media engagement (sites where you often play media), and a Sound "Allow" exception.

Media started from browser UI counts as user input: the global media controls, Picture-in-Picture controls and media keys reach the page as a user activation. An extension's script or message doesn't, even when it carries the activation of a click elsewhere: Chromium lets an extension keep a click's activation for 5 seconds and pass it to the pages it messages or injects script into. uBlock Origin injects its scriptlets into a YouTube tab opened by middle-click while it holds that click's activation, which would otherwise start the video as soon as the tab shows.

A same-document navigation, as YouTube makes when you click a video in a YouTube tab you already used, keeps the document and so its activation: the next video plays even when it starts after the click's 5-second transient activation has ended.

Frames: an iframe may play after input in itself, or in an ancestor when the iframe has autoplay delegated (`allow="autoplay"`, or same-origin). This is Chromium's rule for Permissions Policy; Firefox lets any frame play after input in the top document. A click in an iframe also activates its ancestors, as in Chromium.

Chromium's other exceptions still allow autoplay: an installed web app's own pages, a site with camera or microphone permission, and a page that is capturing camera or microphone.

## Code

`src/chrome/browser/content_settings/autoplay_setting.cc` reads the setting for the top-level URL when a frame is about to commit a new document (`SoundContentSettingObserver::ReadyToCommitNavigation`) and sends blink an autoplay flag for that document, through the existing `AutoplayConfigurationClient`: `kAutoplayFlagForceAllow` for Allow, the new `kAutoplayFlagDocumentInputRequired` for Block, none for Block audio. The flag arrives before the document runs script. Block audio leaves the WebPreferences autoplay policy (`kDocumentUserActivationRequired`) as Chromium sets it. Its checks of the frame's sticky and transient activation use `HadDocumentInput()` and `HasTransientUserActivation()` from `oganesson_autoplay.cc`, so the activation an extension passes on doesn't count there either.

When the page has `kAutoplayFlagDocumentInputRequired`, blink's `AutoplayPolicy` hands three decisions to `src/third_party/blink/renderer/core/html/media/oganesson_autoplay.cc` (hooks in `patches/oganesson/core/autoplay-setting.patch`):

- `IsDocumentAllowedToPlay()` counts only input in the document, walking up to ancestors as before, and skips `HadStickyUserActivationBeforeNavigation()`, media engagement and the Sound exception flag. Web Audio and speech synthesis call this function, so they follow the same rule.
- Transient activation counts only when it is the document's own, and not the opener's.
- Muted video isn't exempt (`DocumentShouldAutoplayMutedVideos()`).

The frame's own sticky activation isn't enough, because Chromium keeps it across same-origin navigations (`StickyUserActivationAcrossSameOriginNavigation`), and a frame reused for the next document also keeps the click's transient activation. So `Frame::NotifyUserActivationInFrame()` marks the window (a `Supplement<LocalDOMWindow>`) on each user activation that isn't the sticky-only state a navigation passes on. A new document has a new window, without the mark.

Limits:

- A parent frame in another process counts with its sticky activation, which a same-origin navigation keeps.
- An out-of-process iframe's renderer keeps the flags of earlier pages in that process for the same tab; with Allow and Block both set, Allow wins.
- Pages that aren't in a tab (extension pages, for example) get no flag and keep Chromium's policy.

The settings page is `src/chrome/browser/resources/settings/site_settings/autoplay_page.ts` (`patches/oganesson/settings/autoplay-settings.patch`), with Chromium's default radio group and exception lists.

`tools/e2e/test_autoplay.py` covers the three choices, an exception and the settings page with local pages. Real YouTube isn't part of the tests.
