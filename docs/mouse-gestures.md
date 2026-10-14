# Mouse gestures

Hold the right mouse button, draw, and release: the browser runs the command the gesture is set to. Out of the box, a stroke to the left goes back.

Gestures work anywhere in the window: on web pages, `chrome://` pages, add-on pages, local files, PDFs, frames from other sites, pages that are busy or block mouse events, in incognito windows, and from the tabs, the toolbar and the side panel. A stroke can cross from one to another, for example up from the page over the toolbar and then along the tabs. The empty part of the tab strip is the window's title bar: a right press there opens the title bar's menu and starts no gesture.

A plain right click is held until release, then replayed at the same place with the same keys, so Shift+right-click still shows the browser's menu on pages that block it. The replayed click goes to what is under the pointer at release: a control the page put there meanwhile, or the new document after a navigation.

## Kinds of gesture

- **Strokes**: draw with the right button held. A gesture is a sequence of directions, `L`, `R`, `U` and `D` (left, right, up, down), for example `DR` for down then right. Repeated directions count once, so a long stroke left is still `L`.
- **Rocker**: hold right and click left, or hold left and click right. Keep clicking the second button while the first stays held to repeat the command, for example to go through tabs.
- **Wheel**: hold right and scroll up or down. It runs once per wheel notch, so keep scrolling to repeat it, for example to go through tabs. Once a rocker or wheel command has run, releasing the right button runs no stroke.

A gesture that isn't set does nothing. A plain right click still opens the context menu. Escape, switching to another window, a menu that opens during the stroke, moving the window, or a tab switch you didn't make with the gesture cancels a stroke in progress. A cancelled stroke runs nothing, and the page gets neither the press nor the release. A stroke released outside the window still runs. Tab switches made by the gesture's own command, such as wheel or rocker tab cycling, don't.

## Setting gestures

Open Settings, then **System → Shortcuts and gestures** (`chrome://settings/system/shortcuts`). On a command's row, **Add gesture** opens a dialog: pick the kind of gesture, and for a stroke type its directions, such as `DR`. A gesture shows as a chip on the row; remove the chip to remove the gesture.

Add-on commands are listed under **Extension commands**, each with its gestures.

Gestures can run the commands listed on that page, including add-ons' commands under **Extension commands**.

## Letting the page have the right button

- Hold **Ctrl** when you press the right button, or press it during a stroke, to send the right button to the page instead. The stroke you drew before pressing Ctrl does nothing.
- While a page has locked the pointer, as games do, gestures don't start and the page gets the right button.
- Add-ons that draw their own gestures in pages, such as Gesturefy, only work when oganesson's gestures are off: remove every gesture on the Shortcuts and gestures page.

## Limits

- Linux only, on X11 and Wayland. Touchpad scrolling doesn't trigger wheel gestures.
- Not tested, because they need hardware the test display doesn't have: screens with different scale factors, and touchpads (#2).
- Native file pickers, system menus and window decorations drawn by the desktop don't see gestures.
