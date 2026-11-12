// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

// Linux: the windows' icon (X11's _NET_WM_ICON, Wayland's xdg-toplevel-icon)
// and the icon of the browser's .desktop entry, which docks and app menus
// show. That entry is a copy of the installed one in the user's own
// applications folder, which comes first, with Icon= naming the variant's PNG
// in the install's app_icons/ folder.

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "base/containers/span.h"
#include "base/environment.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/functional/bind.h"
#include "base/nix/xdg_util.h"
#include "base/path_service.h"
#include "base/strings/string_split.h"
#include "base/strings/string_util.h"
#include "base/task/thread_pool.h"
#include "chrome/browser/ui/app_icon/oganesson_app_icon.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface_iterator.h"
#include "chrome/common/channel_info.h"
#include "chrome/grit/chrome_unscaled_resources.h"
#include "ui/base/base_window.h"
#include "ui/base/resource/resource_bundle.h"
#include "ui/gfx/image/image.h"
#include "ui/gfx/image/image_skia.h"
#include "ui/views/widget/native_widget_private.h"
#include "ui/views/widget/widget.h"

namespace oganesson_app_icon {

namespace {

// The first line of a .desktop entry this file wrote: one without it is the
// user's own, which it leaves alone.
constexpr char kMarker[] =
    "# Written by oganesson for Settings > Appearance > App icon.";

// The chosen icon, a null image for the default. Made once and never freed:
// windows may hold on to it.
gfx::ImageSkia* g_icon = nullptr;
// Counts Apply() calls, so only the last one's file read sets the icon.
int g_generation = 0;

base::FilePath VariantPng(size_t index) {
  base::FilePath exe_dir;
  base::PathService::Get(base::DIR_EXE, &exe_dir);
  return exe_dir.Append("app_icons")
      .AppendASCII(std::string(kVariants[index]) + ".png");
}

// The installed entry with Icon= set to `icon` and TryExec= to its Exec=
// program, so menus hide the copy once the browser is uninstalled.
std::string CopyWithIcon(const std::string& installed,
                         const base::FilePath& icon) {
  std::vector<std::string> lines = base::SplitString(
      installed, "\n", base::KEEP_WHITESPACE, base::SPLIT_WANT_NONEMPTY);
  std::string program;
  for (const std::string& line : lines) {
    if (program.empty() && base::StartsWith(line, "Exec=")) {
      program = line.substr(5, line.find(' ') - 5);
    }
  }
  std::string copy = std::string(kMarker) + "\n";
  for (const std::string& line : lines) {
    if (base::StartsWith(line, "Icon=") || base::StartsWith(line, "TryExec=")) {
      continue;
    }
    copy += line + "\n";
    if (line == "[Desktop Entry]") {
      copy += "Icon=" + icon.value() + "\n";
      if (!program.empty()) {
        copy += "TryExec=" + program + "\n";
      }
    }
  }
  return copy;
}

// Writes or removes the user's copy of the browser's .desktop entry. Blocks.
void UpdateDesktopEntry(size_t index) {
  std::unique_ptr<base::Environment> env = base::Environment::Create();
  base::FilePath name(chrome::GetDesktopName(env.get()));
  base::FilePath user_dir =
      base::nix::GetXDGDataWriteLocation(env.get()).Append("applications");
  base::FilePath user_entry = user_dir.Append(name);

  std::string current;
  if (base::ReadFileToString(user_entry, &current) &&
      !base::StartsWith(current, kMarker)) {
    return;
  }
  base::FilePath icon = VariantPng(index);
  std::string installed;
  for (const base::FilePath& dir :
       base::nix::GetXDGDataSearchLocations(env.get())) {
    base::FilePath entry = dir.Append("applications").Append(name);
    if (entry != user_entry && base::ReadFileToString(entry, &installed)) {
      break;
    }
  }
  // The default, an install without a .desktop entry (an unpacked archive)
  // or one without the variant's file: the installed entry as it is.
  if (index == 0 || installed.empty() || !base::PathExists(icon)) {
    if (!current.empty()) {
      base::DeleteFile(user_entry);
    }
    return;
  }
  std::string copy = CopyWithIcon(installed, icon);
  if (copy != current && base::CreateDirectory(user_dir)) {
    base::WriteFile(user_entry, copy);
  }
}

std::optional<std::string> UpdateDesktopEntryAndReadIcon(size_t index) {
  UpdateDesktopEntry(index);
  std::string png;
  if (index == 0 || !base::ReadFileToString(VariantPng(index), &png)) {
    return std::nullopt;
  }
  return png;
}

void SetIcon(int generation, std::optional<std::string> png) {
  if (generation != g_generation) {
    return;
  }
  if (!g_icon) {
    g_icon = new gfx::ImageSkia();
  }
  *g_icon = png ? gfx::Image::CreateFrom1xPNGBytes(base::as_byte_span(*png))
                      .AsImageSkia()
                : gfx::ImageSkia();
  const gfx::ImageSkia* icon = GetWindowIcon();
  if (!icon) {
    icon = ui::ResourceBundle::GetSharedInstance().GetImageSkiaNamed(
        IDR_PRODUCT_LOGO_128);
  }
  // As DesktopWindowTreeHostLinux sets the icon on a new window. Web apps
  // have their own.
  for (BrowserWindowInterface* window : GetAllBrowserWindowInterfaces()) {
    if (window->GetType() != BrowserWindowInterface::Type::TYPE_NORMAL) {
      continue;
    }
    views::Widget* widget = views::Widget::GetWidgetForNativeWindow(
        window->GetWindow()->GetNativeWindow());
    if (widget && widget->native_widget_private()) {
      widget->native_widget_private()->SetWindowIcons(gfx::ImageSkia(), *icon);
    }
  }
}

}  // namespace

gfx::ImageSkia* GetWindowIcon() {
  return g_icon && !g_icon->isNull() ? g_icon : nullptr;
}

void Apply(size_t index) {
  base::ThreadPool::PostTaskAndReplyWithResult(
      FROM_HERE, {base::MayBlock(), base::TaskPriority::USER_VISIBLE},
      base::BindOnce(&UpdateDesktopEntryAndReadIcon, index),
      base::BindOnce(&SetIcon, ++g_generation));
}

}  // namespace oganesson_app_icon
