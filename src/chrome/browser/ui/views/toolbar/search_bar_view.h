// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_VIEWS_TOOLBAR_SEARCH_BAR_VIEW_H_
#define CHROME_BROWSER_UI_VIEWS_TOOLBAR_SEARCH_BAR_VIEW_H_

#include <memory>
#include <string>
#include <vector>

#include "base/memory/raw_ptr.h"
#include "base/scoped_observation.h"
#include "components/prefs/pref_change_registrar.h"
#include "components/search_engines/template_url_service.h"
#include "components/search_engines/template_url_service_observer.h"
#include "ui/base/metadata/metadata_header_macros.h"
#include "ui/menus/simple_menu_model.h"
#include "ui/views/controls/textfield/textfield_controller.h"
#include "ui/views/view.h"

class BrowserWindowInterface;
class TemplateURL;
class ToolbarButton;

namespace views {
class MenuRunner;
class Textfield;
}  // namespace views

// Firefox's separate search bar: a search box in the toolbar with its own
// engine. Shown when prefs::kSearchBarVisible is set; the engine is
// prefs::kSearchBarEngine, or the default search engine.
class SearchBarView : public views::View,
                      public views::TextfieldController,
                      public ui::SimpleMenuModel::Delegate,
                      public TemplateURLServiceObserver {
  METADATA_HEADER(SearchBarView, views::View)

 public:
  explicit SearchBarView(BrowserWindowInterface* browser);
  SearchBarView(const SearchBarView&) = delete;
  SearchBarView& operator=(const SearchBarView&) = delete;
  ~SearchBarView() override;

  // Opens the engine menu; it is also what drags the search bar around the
  // toolbar.
  ToolbarButton* engine_button() { return engine_button_; }

  // views::TextfieldController:
  bool HandleKeyEvent(views::Textfield* sender,
                      const ui::KeyEvent& key_event) override;

  // ui::SimpleMenuModel::Delegate:
  void ExecuteCommand(int command_id, int event_flags) override;
  bool IsCommandIdChecked(int command_id) const override;

  // TemplateURLServiceObserver:
  void OnTemplateURLServiceChanged() override;

 private:
  const TemplateURL* GetEngine() const;
  void UpdateEngine();
  void ShowEngineMenu();

  const raw_ptr<BrowserWindowInterface> browser_;
  const raw_ptr<TemplateURLService> template_urls_;
  raw_ptr<ToolbarButton> engine_button_ = nullptr;
  raw_ptr<views::Textfield> textfield_ = nullptr;
  // The engines in the open menu, by command id.
  std::vector<std::string> menu_guids_;
  std::unique_ptr<ui::SimpleMenuModel> menu_model_;
  std::unique_ptr<views::MenuRunner> menu_runner_;
  PrefChangeRegistrar prefs_;
  base::ScopedObservation<TemplateURLService, TemplateURLServiceObserver>
      template_urls_observation_{this};
};

#endif  // CHROME_BROWSER_UI_VIEWS_TOOLBAR_SEARCH_BAR_VIEW_H_
