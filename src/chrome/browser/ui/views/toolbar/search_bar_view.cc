// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/views/toolbar/search_bar_view.h"

#include <utility>

#include "base/functional/bind.h"
#include "base/strings/strcat.h"
#include "base/strings/string_util.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/search_engines/template_url_service_factory.h"
#include "chrome/browser/ui/browser_window/public/browser_window_interface.h"
#include "chrome/browser/ui/navigator/browser_navigator.h"
#include "chrome/browser/ui/navigator/browser_navigator_params.h"
#include "chrome/browser/ui/layout_constants.h"
#include "chrome/browser/ui/views/toolbar/toolbar_button.h"
#include "chrome/common/pref_names.h"
#include "chrome/grit/generated_resources.h"
#include "components/prefs/pref_service.h"
#include "components/search_engines/template_url.h"
#include "components/vector_icons/vector_icons.h"
#include "net/http/http_request_headers.h"
#include "services/network/public/cpp/resource_request_body.h"
#include "ui/base/l10n/l10n_util.h"
#include "ui/base/metadata/metadata_impl_macros.h"
#include "ui/base/mojom/menu_source_type.mojom.h"
#include "ui/base/page_transition_types.h"
#include "ui/base/window_open_disposition.h"
#include "ui/events/event.h"
#include "ui/views/accessibility/view_accessibility.h"
#include "ui/views/controls/menu/menu_runner.h"
#include "ui/views/controls/textfield/textfield.h"
#include "ui/views/layout/flex_layout.h"
#include "ui/views/view_class_properties.h"
#include "url/gurl.h"

namespace {

// Firefox's default search bar width is about this.
constexpr int kSearchBarWidth = 250;

}  // namespace

SearchBarView::SearchBarView(BrowserWindowInterface* browser)
    : browser_(browser),
      template_urls_(
          TemplateURLServiceFactory::GetForProfile(browser->GetProfile())) {
  SetLayoutManager(std::make_unique<views::FlexLayout>())
      ->SetOrientation(views::LayoutOrientation::kHorizontal)
      .SetCrossAxisAlignment(views::LayoutAlignment::kCenter);
  SetPreferredSize(gfx::Size(
      kSearchBarWidth, GetLayoutConstant(LayoutConstant::kToolbarButtonHeight)));

  engine_button_ = AddChildView(std::make_unique<ToolbarButton>(
      base::BindRepeating(&SearchBarView::ShowEngineMenu,
                          base::Unretained(this))));
  engine_button_->SetVectorIcon(vector_icons::kSearchIcon);
  const std::u16string engine_label =
      l10n_util::GetStringUTF16(IDS_SEARCH_BAR_ENGINE_BUTTON);
  engine_button_->SetTooltipText(engine_label);
  engine_button_->GetViewAccessibility().SetName(engine_label);

  textfield_ = AddChildView(std::make_unique<views::Textfield>());
  textfield_->set_controller(this);
  textfield_->SetProperty(
      views::kFlexBehaviorKey,
      views::FlexSpecification(views::MinimumFlexSizeRule::kScaleToZero,
                               views::MaximumFlexSizeRule::kUnbounded));

  prefs_.Init(browser->GetProfile()->GetPrefs());
  prefs_.Add(prefs::kSearchBarVisible,
             base::BindRepeating(
                 [](SearchBarView* view) {
                   view->SetVisible(view->prefs_.prefs()->GetBoolean(
                       prefs::kSearchBarVisible));
                 },
                 base::Unretained(this)));
  prefs_.Add(prefs::kSearchBarEngine,
             base::BindRepeating(&SearchBarView::UpdateEngine,
                                 base::Unretained(this)));
  SetVisible(prefs_.prefs()->GetBoolean(prefs::kSearchBarVisible));

  if (template_urls_) {
    template_urls_observation_.Observe(template_urls_);
    template_urls_->Load();
  }
  UpdateEngine();
}

SearchBarView::~SearchBarView() = default;

bool SearchBarView::HandleKeyEvent(views::Textfield* sender,
                                   const ui::KeyEvent& key_event) {
  if (key_event.type() != ui::EventType::kKeyPressed ||
      key_event.key_code() != ui::VKEY_RETURN) {
    return false;
  }
  const TemplateURL* engine = GetEngine();
  const std::u16string terms(
      base::TrimWhitespace(textfield_->GetText(), base::TRIM_ALL));
  if (!engine || terms.empty()) {
    return true;
  }
  TemplateURLRef::PostContent post_content;
  const GURL url(engine->url_ref().ReplaceSearchTerms(
      TemplateURLRef::SearchTermsArgs(terms),
      template_urls_->search_terms_data(), &post_content));
  if (!url.is_valid()) {
    return true;
  }
  NavigateParams params(browser_, url, ui::PAGE_TRANSITION_GENERATED);
  // An engine with search_url_post_params takes the terms as a POST body.
  if (!post_content.second.empty()) {
    params.post_data = network::ResourceRequestBody::CreateFromCopyOfBytes(
        base::as_byte_span(post_content.second));
    params.extra_headers = base::StrCat({net::HttpRequestHeaders::kContentType,
                                         ": ", post_content.first, "\r\n"});
  }
  // Alt+Enter opens a new tab in Firefox; Ctrl+Enter as well here.
  params.disposition = key_event.IsAltDown() || key_event.IsControlDown()
                           ? WindowOpenDisposition::NEW_FOREGROUND_TAB
                           : WindowOpenDisposition::CURRENT_TAB;
  Navigate(&params);
  return true;
}

void SearchBarView::ExecuteCommand(int command_id, int event_flags) {
  prefs_.prefs()->SetString(prefs::kSearchBarEngine,
                            menu_guids_[command_id]);
}

bool SearchBarView::IsCommandIdChecked(int command_id) const {
  const TemplateURL* engine = GetEngine();
  return engine && engine->sync_guid() == menu_guids_[command_id];
}

void SearchBarView::OnTemplateURLServiceChanged() {
  UpdateEngine();
}

const TemplateURL* SearchBarView::GetEngine() const {
  if (!template_urls_ || !template_urls_->loaded()) {
    return nullptr;
  }
  const TemplateURL* chosen = template_urls_->GetTemplateURLForGUID(
      prefs_.prefs()->GetString(prefs::kSearchBarEngine));
  return chosen ? chosen : template_urls_->GetDefaultSearchProvider();
}

void SearchBarView::UpdateEngine() {
  const TemplateURL* engine = GetEngine();
  const std::u16string placeholder =
      engine ? l10n_util::GetStringFUTF16(IDS_SEARCH_BAR_PLACEHOLDER,
                                          engine->short_name())
             : std::u16string();
  textfield_->SetPlaceholderText(placeholder);
  textfield_->GetViewAccessibility().SetName(placeholder);
}

void SearchBarView::ShowEngineMenu() {
  if (!template_urls_ || !template_urls_->loaded()) {
    return;
  }
  menu_guids_.clear();
  menu_model_ = std::make_unique<ui::SimpleMenuModel>(this);
  for (const TemplateURL* engine : template_urls_->GetTemplateURLs()) {
    // The search engines and the active site searches, as listed in
    // settings, without the @-shortcuts or extension keywords.
    if (engine->type() == TemplateURL::NORMAL &&
        engine->data().starter_pack_id == 0 &&
        (template_urls_->ShowInDefaultList(engine) ||
         template_urls_->ShowInActivesList(engine))) {
      menu_model_->AddCheckItem(menu_guids_.size(), engine->short_name());
      menu_guids_.push_back(engine->sync_guid());
    }
  }
  menu_runner_ = std::make_unique<views::MenuRunner>(
      menu_model_.get(), views::MenuRunner::HAS_MNEMONICS);
  menu_runner_->RunMenuAt(GetWidget(), nullptr,
                          engine_button_->GetAnchorBoundsInScreen(),
                          views::MenuAnchorPosition::kTopLeft,
                          ui::mojom::MenuSourceType::kMouse);
}

BEGIN_METADATA(SearchBarView)
END_METADATA
