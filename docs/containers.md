# Containers

A container keeps its own cookies and site storage within one profile, as Firefox's Multi-Account Containers and Brave's containers do. A tab in the Work container is signed in to Work's accounts, and a tab outside containers doesn't see them. Containers are for regular profiles: incognito and guest windows have none.

The code is a port of Brave's containers (`brave-core` main of 2026-11-08, MPL-2.0), rewritten so that it touches Chromium in a few lines. The shared part is in dubna (`src/chrome/browser/containers/`); the desktop part is in `src/chrome/browser/containers/platform/`.

## Using them

- **New tab in container**: right-click the New Tab button.
- **Open link in container**: in a link's context menu.
- **Reopen in container**: in a tab's context menu. The tab reopens in its place in the chosen container, or outside containers with **No container**.
- **Open in container**: in a bookmark's or bookmark folder's context menu.
- Each of these menus offers **New temporary container** and **Manage containers…**.
- **Commands**: Ctrl+Shift+1 to Ctrl+Shift+9 open a new tab in the first nine containers of the list. "New tab in the current tab's container" has no shortcut. Settings > System > Keyboard shortcuts lists them, to change their shortcuts.

A container tab has a line in the container's color along its bottom, as in Firefox, in the horizontal and the vertical tab strip. The address bar shows its container's icon, with the container's name in the tooltip; a click on it opens the menu to reopen the tab in another container.

A link a container tab opens stays in the container, whether it opens in the same tab, a new tab (middle click, `target=_blank`, `window.open`, with or without `noopener`) or a new window. So do a link dropped on the tab strip and an address opened with Alt+Enter while a container tab is shown. New tabs from the New Tab button or a bookmark open outside containers, unless Settings says otherwise (below).

**Settings > Privacy and security > Containers** (`chrome://settings/containers`) lists the containers: add one, change its name, color or icon, or delete it. A new profile has Firefox's four: Personal, Work, Banking and Shopping. Its **Open new tabs in** says where the New Tab button and Ctrl+T open a tab: outside containers (the default), in a container, or in a new temporary container each time, as Brave's pull request brave-core#40693 does. With its **Ask every time**, a click on the New Tab button shows the menu of containers, with **No container** first, and Ctrl+T opens a tab outside containers.

Deleting a container closes its tabs and forgets its closed tabs. Its cookies and site data are deleted then, or at the next start when a tab of it stayed open (a page that asks before it closes) or the last session, which the user can still restore, had a tab in it.

A temporary container gets a name such as "Temporary 2" and a random color. Its data is deleted at a start once no tab, closed tab or restorable session uses it.

### Traffic Control

The same Settings page has Traffic Control's rules: sites that match a rule open in its container, a new temporary container each time, or outside containers, whichever tab they start in. A rule's sites are patterns of the URL blocklist policy's format (`example.com`, `https://*.example.org/path`), one per line; lines that start with `#` are comments. The first enabled rule that matches wins.

A navigation that a rule sends elsewhere stops, and its page opens in a new tab in the rule's container beside its tab. The tab it started in closes when it was an empty new tab, unless a page holds it as its `window.opener` (an OAuth popup). A tab that browses within one site stays where it is, unless the address was typed, so a page the user opened in another container on purpose stays there. Reloads, back and forward, and restored tabs never move.

## Sync

Containers and Traffic Control's one-site rules (`.example.com`) sync with Firefox's Multi-Account Containers add-on through Firefox Sync, as the add-on's own `storage.sync` data ([Firefox Sync](firefox-sync.md#containers)). Rules with other patterns, temporary containers, and the containers' order stay on this device.

## How it works

Each container is a storage partition: domain `containers`, named by the container's id. Chromium keeps every navigation of a SiteInstance with a fixed storage partition in that partition, so a tab is in a container from the moment its WebContents is created in it, and stays there. The browser therefore only has to create tabs in the right partition:

| Where a tab is made | How it gets its container |
|---|---|
| The menus, Traffic Control, pinned tabs at startup | `NavigateInContainer()` creates the WebContents in the container's partition and inserts it. |
| A link to a new tab without an opener (middle click, the context menu's "Open link in new tab") | `browser_navigator.cc` takes the container of the page that opens it (`InheritContainer()`). |
| A link dropped on the tab strip, Alt+Enter in the address bar | `NavigateFromActiveTab()` opens it in the active tab's container. |
| A window a page opens without an opener (`target=_blank`, `noopener`) | `web_contents_impl.cc` keeps the page's partition, for container partitions only, as content does for guests. |
| A window a page opens with an opener (`window.open`) | Chromium already uses the opener's SiteInstance. |
| A restored tab, after a restart or reopened | `browser_tabrestore.cc` asks `SiteInstanceToRestore()`, which reads the container that the session saved. |

Sessions and closed tabs save each page's container as the page's extended info (`sessions::ExtendedInfoHandler`, key `containers.id`), which is upstream's own way to add data to saved navigations. The handler is registered as the first tab goes into a container: Chrome creates the first profile before it sets up its navigation driver, so the service is too early. Brave encodes the container into the saved URL and page state instead (`containers+<id>:https://…`), which needs hooks in sessions, content and Blink. A page of the browser itself (`chrome://`) restores outside containers, as in Brave.

Pinned tabs that open at startup without the session (Settings > On startup > Open the New Tab page) are saved by `pinned_tab_codec.cc`, which keeps the container next to the URL.

### Prefs

All per profile, in `container.h`:

| Pref | What |
|---|---|
| `containers.list` | The user's containers, in order: `{id, name, icon, color}`. Icons and colors are Firefox's names. |
| `containers.used` | The containers whose storage may be on disk, by id, with their name, icon and color: used ones of the list, temporary ones, and deleted ones until their storage is gone. |
| `containers.traffic_control` | Traffic Control's rules, in order: `{url_filter, container, enabled}`. `container` is an id, `temporary`, or empty for outside containers. |
| `containers.new_tab` | Where new tabs open: an id, `temporary`, `ask` (desktop only: the New Tab button asks), or empty. |

The Settings page edits the two lists and `containers.new_tab` through `settingsPrivate`, and the browser follows the prefs: a container gone from the list is a deleted one.

## Chromium hooks

Lines are the lines a patch adds or changes, includes counted. Shared, in `dubna/patches/containers.patch`:

| File | Lines | Why |
|---|---|---|
| `content/browser/web_contents/web_contents_impl.cc` | 5 | A window opened without an opener gets a new default SiteInstance: no upstream hook gives it a partition. |
| `content/browser/renderer_host/navigation_entry_impl.cc` | 11 | The partition a page committed in, which the session handler saves. The public `NavigationEntry` doesn't tell its SiteInstance. |
| `components/permissions/permission_util.cc` | 7 | Notifications: Chromium blocks them in a partition that isn't the site's own. |
| `chrome/browser/profiles/chrome_browser_main_extra_parts_profiles.cc` | 2 | Builds the service factory at startup, which registers the prefs. |
| `chrome/browser/chrome_content_browser_client_navigation_throttles.cc` | 2 | Traffic Control's throttle. |
| `chrome/browser/BUILD.gn` | 1 | Links `//chrome/browser/containers/platform`. |

Desktop, in `patches/oganesson/core/containers.patch`:

| File | Lines | Why |
|---|---|---|
| `chrome/app/chrome_command_ids.h` | 11 | The submenus' command ids, and the commands'. |
| `chrome/browser/ui/navigator/browser_navigator.cc` | 5 | A new tab without an opener takes its source page's container. `NavigateParams` has no partition. |
| `chrome/browser/ui/browser_tabrestore.cc` | 3 | A restored tab's SiteInstance. |
| `chrome/browser/ui/browser_tabstrip.cc` | 5 | A new tab opens in the container Settings says. |
| `chrome/browser/ui/startup/startup_tab.h`, `pinned_tab_codec.cc`, `startup_browser_creator_impl.cc` | 16 | Pinned tabs at startup keep their container. |
| `chrome/browser/ui/browser_commands.cc` (Alt+Enter), `views/frame/browser_root_view.cc` (a dropped link) | 4 | `NavigateFromActiveTab()` instead of `Navigate()`. |
| `chrome/browser/ui/browser_command_controller.cc` | 7 | Enables and runs the commands (`CommandIds()`, `ExecuteCommand()`). |
| `chrome/browser/ui/accelerator_table.cc` | 19 | Ctrl+Shift+1 to 9. Chromium uses none of them. |
| `chrome/browser/ui/browser_shortcuts/browser_shortcut_metadata.cc` | 10 | The commands' names on Helium's shortcuts page. |

In `patches/oganesson/ui/containers-menus.patch`, each menu adds its submenu in 3 to 4 lines and keeps it in one member: `render_view_context_menu.cc/.h`, `tab_menu_model.cc/.h`, `new_tab_button_menu_model.cc/.h` (upstream's New Tab button menu) and `bookmark_context_menu_controller.cc/.h`. Each submenu item takes an upstream command id whose enablement fits, as Send to device does, so no menu's enablement code changes. `tab.cc` and the vertical strip's `tabs/common/tab_view.cc` draw the color line (1 line each). For "Ask every time", the New Tab button shows the menu of containers (`ContainersMenu::AskForNewTab()`) from `tab_strip.cc` and, for the vertical strip, `tabs/shared/new_tab_button.cc` (4 lines each).

`patches/oganesson/ui/containers-page-action.patch` adds the address bar icon (`container_page_action.cc`), as upstream adds its page actions: an action id (`chrome_action_id.h`, `action_ids.h`), an icon type and properties (`page_action_icon_type.h`, `page_action_properties_provider.cc`), the browser's action that the click runs (`browser_actions.cc`, 3 lines) and the per-tab controller (`tab_features.cc/.h`, 6 lines), 22 lines in all.

`patches/oganesson/settings/containers-settings.patch` adds the Settings route, its row under Privacy and security, and the lazy-loaded page, as other pages of ours do.

## Not done

- The WebExtensions `contextualIdentities` API and a proxy per container are later tasks (goals.md).
- Zoom levels are per partition, so a container keeps its own zoom levels. Brave makes containers share the default ones with another content hook.
