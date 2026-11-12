// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Windows: chrome.exe carries the variants as icons after Chromium's own
// (chrome_exe.rc), so a shortcut can name one by its index, as it names the
// default with index 0. This sets the windows' icons and the icon of the
// shortcuts that start the browser: on the desktop, in the Start menu and on
// the taskbar.

#include <windows.h>

#include <iterator>

#include "base/files/file_enumerator.h"
#include "base/files/file_path.h"
#include "base/functional/bind.h"
#include "base/path_service.h"
#include "base/task/single_thread_task_runner.h"
#include "base/task/thread_pool.h"
#include "base/win/shortcut.h"
#include "chrome/browser/ui/app_icon/oganesson_app_icon.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface_iterator.h"
#include "chrome/browser/win/app_icon.h"
#include "ui/base/base_window.h"
#include "ui/views/win/hwnd_util.h"

namespace oganesson_app_icon {

namespace {

// chrome.exe's icons, as chrome_exe.rc names them for a Chromium build: the
// variants after kVariants[0] follow IDR_X009_OMNIBOX_EVERYWHERE, the 7th.
// Named icons are numbered in the order of their names.
constexpr const wchar_t* kResourceNames[] = {
    nullptr,
    L"IDR_X010_OGANESSON_TEAL",
    L"IDR_X011_OGANESSON_CRIMSON",
    L"IDR_X012_OGANESSON_BLACK",
    L"IDR_X013_OGANESSON_WHITE",
    L"IDR_X014_OGANESSON_CLEAR_WHITE",
    L"IDR_X015_OGANESSON_CLEAR_BLACK"};
static_assert(std::size(kResourceNames) == std::size(kVariants));
constexpr int kFirstVariantIconIndex = 7;

size_t g_index = 0;

int IconIndex(size_t index) {
  return index == 0 ? 0 : kFirstVariantIconIndex + static_cast<int>(index) - 1;
}

HICON LoadVariantIcon(size_t index, bool small_icon) {
  int metric_x = small_icon ? SM_CXSMICON : SM_CXICON;
  int metric_y = small_icon ? SM_CYSMICON : SM_CYICON;
  // Shared: the system keeps one copy, which needs no DestroyIcon.
  return static_cast<HICON>(LoadImage(
      GetModuleHandle(nullptr), kResourceNames[index], IMAGE_ICON,
      GetSystemMetrics(metric_x), GetSystemMetrics(metric_y), LR_SHARED));
}

// Points the shortcuts that start the browser, with no arguments, at variant
// `index`'s icon. Leaves those of profiles and web apps, which have arguments,
// and those it can't write (all users' ones without admin rights). Blocks.
void UpdateShortcuts(size_t index) {
  base::FilePath exe;
  if (!base::PathService::Get(base::FILE_EXE, &exe)) {
    return;
  }
  const int folders[] = {base::DIR_USER_DESKTOP, base::DIR_COMMON_DESKTOP,
                         base::DIR_START_MENU, base::DIR_COMMON_START_MENU,
                         base::DIR_TASKBAR_PINS};
  for (int key : folders) {
    base::FilePath folder;
    if (!base::PathService::Get(key, &folder)) {
      continue;
    }
    base::FileEnumerator links(folder, false, base::FileEnumerator::FILES,
                               FILE_PATH_LITERAL("*.lnk"));
    for (base::FilePath link = links.Next(); !link.empty();
         link = links.Next()) {
      base::win::ShortcutProperties current;
      if (!base::win::ResolveShortcutProperties(
              link,
              base::win::ShortcutProperties::PROPERTIES_TARGET |
                  base::win::ShortcutProperties::PROPERTIES_ARGUMENTS |
                  base::win::ShortcutProperties::PROPERTIES_ICON,
              &current) ||
          !base::FilePath::CompareEqualIgnoreCase(current.target.value(),
                                                  exe.value()) ||
          !current.arguments.empty()) {
        continue;
      }
      // A shortcut with no icon of its own shows chrome.exe's first.
      bool unset = current.icon.empty() && index == 0;
      bool same = current.icon_index == IconIndex(index) &&
                  base::FilePath::CompareEqualIgnoreCase(current.icon.value(),
                                                         exe.value());
      if (unset || same) {
        continue;
      }
      base::win::ShortcutProperties icon;
      icon.set_icon(exe, IconIndex(index));
      base::win::CreateOrUpdateShortcutLink(
          link, icon, base::win::ShortcutOperation::kUpdateExisting);
    }
  }
}

}  // namespace

HICON GetWindowIcon(bool small_icon) {
  if (g_index == 0) {
    return nullptr;
  }
  return LoadVariantIcon(g_index, small_icon);
}

void Apply(size_t index) {
  g_index = index;
  HICON big = GetWindowIcon(false);
  HICON small_icon = GetWindowIcon(true);
  if (!big || !small_icon) {
    big = GetAppIcon();
    small_icon = GetSmallAppIcon();
  }
  // New windows take the icon from their window class, which
  // ChromeViewsDelegate gives this one; open ones are told. Web apps have
  // their own.
  for (BrowserWindowInterface* window : GetAllBrowserWindowInterfaces()) {
    if (window->GetType() != BrowserWindowInterface::Type::TYPE_NORMAL) {
      continue;
    }
    HWND hwnd =
        views::HWNDForNativeWindow(window->GetWindow()->GetNativeWindow());
    if (hwnd) {
      SendMessage(hwnd, WM_SETICON, ICON_BIG, reinterpret_cast<LPARAM>(big));
      SendMessage(hwnd, WM_SETICON, ICON_SMALL,
                  reinterpret_cast<LPARAM>(small_icon));
    }
  }
  base::ThreadPool::CreateCOMSTATaskRunner(
      {base::MayBlock(), base::TaskPriority::BEST_EFFORT})
      ->PostTask(FROM_HERE, base::BindOnce(&UpdateShortcuts, index));
}

}  // namespace oganesson_app_icon
