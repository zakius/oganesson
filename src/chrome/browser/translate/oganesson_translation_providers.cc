// Copyright 2026 The oganesson Authors
// You can use, redistribute, and/or modify this source code under
// the terms of the GPL-3.0 license that can be found in the LICENSE file.

#include "chrome/browser/translate/oganesson_translation_providers.h"

#include <algorithm>
#include <iterator>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "base/functional/bind.h"
#include "base/functional/callback.h"
#include "base/functional/callback_helpers.h"
#include "base/json/json_reader.h"
#include "base/memory/raw_ref.h"
#include "base/memory/scoped_refptr.h"
#include "base/memory/weak_ptr.h"
#include "base/no_destructor.h"
#include "base/scoped_observation.h"
#include "base/strings/escape.h"
#include "base/strings/string_util.h"
#include "base/strings/utf_string_conversions.h"
#include "base/time/time.h"
#include "base/timer/timer.h"
#include "base/types/expected.h"
#include "base/values.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/component_updater/translate_kit_component_installer.h"
#include "chrome/browser/component_updater/translate_kit_language_pack_component_installer.h"
#include "chrome/browser/ui/simple_message_box.h"
#include "chrome/grit/oganesson_strings.h"
#include "components/component_updater/component_updater_service.h"
#include "components/crx_file/id_util.h"
#include "components/on_device_translation/installer.h"
#include "components/on_device_translation/public/language_pack.h"
#include "components/on_device_translation/public/mojom/translator.mojom.h"
#include "components/on_device_translation/public/supported_languages.h"
#include "components/on_device_translation/service/service_launcher.h"
#include "components/on_device_translation/service_controller.h"
#include "components/on_device_translation/translation_manager_util.h"
#include "components/translate/content/browser/frame_session_factory.h"
#include "components/translate/core/browser/translation_provider.h"
#include "components/translate/core/common/oganesson_translation.h"
#include "components/translate/core/common/translate_errors.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/navigation_entry.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/storage_partition.h"
#include "content/public/browser/web_contents.h"
#include "mojo/public/cpp/bindings/callback_helpers.h"
#include "mojo/public/cpp/bindings/remote.h"
#include "net/base/url_util.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/network/public/cpp/resource_request.h"
#include "services/network/public/cpp/shared_url_loader_factory.h"
#include "services/network/public/cpp/simple_url_loader.h"
#include "ui/base/l10n/l10n_util.h"
#include "url/gurl.h"

namespace oganesson_translation {

namespace {

using on_device_translation::LanguagePackKey;
using on_device_translation::OnDeviceTranslationController;
using on_device_translation::OnDeviceTranslationInstaller;
using translate::TranslateErrors;

Engine CurrentEngine() {
  return GetEngine(g_browser_process->local_state());
}

// Google Translate's keyless endpoint, the one its own website widget and
// many browser add-ons use: no API key, the page text in the request. Split
// so domain substitution leaves the host alone.
constexpr char kGoogleTranslateURL[] =
    "https://translate.google"
    "apis.com/translate_a/t";

// Larger replies are not translations of a batch the page script sends.
constexpr size_t kMaxReplySize = 1024 * 1024;

constexpr net::NetworkTrafficAnnotationTag kGoogleTranslateAnnotation =
    net::DefineNetworkTrafficAnnotation("oganesson_google_translate", R"(
        semantics {
          sender: "Translation"
          description:
            "Sends the text of a page to Google Translate and gets its "
            "translation."
          trigger:
            "The user translates a page, or a page in a language the user "
            "chose to always translate loads, while Settings > Languages > "
            "Translation is on with Google Translate."
          data: "The page's text, and its language and the target language."
          destination: GOOGLE_OWNED_SERVICE
        }
        policy {
          cookies_allowed: NO
          setting:
            "Settings > Languages > Translation: off, or on this device."
          policy_exception_justification: "Not implemented."
        })");

// Translates through Google Translate, one request per batch of the page
// script, in the page's own network context. The reply lists one translation
// per text, each with its detected language when the source is "auto".
class GoogleSession : public translate::PlainTextTranslationSession {
 public:
  explicit GoogleSession(
      scoped_refptr<network::SharedURLLoaderFactory> loader_factory)
      : loader_factory_(std::move(loader_factory)) {}

 protected:
  void TranslateTexts(const std::string& source_lang,
                      const std::string& target_lang,
                      std::vector<std::u16string> texts,
                      TextsCallback callback) override {
    GURL url(kGoogleTranslateURL);
    url = net::AppendQueryParameter(url, "client", "gtx");
    url = net::AppendQueryParameter(url, "sl", source_lang);
    url = net::AppendQueryParameter(url, "tl", target_lang);
    std::vector<std::string> fields;
    for (const std::u16string& text : texts) {
      // The endpoint decodes HTML entities in the text, so a page's literal
      // "&lt;" would come back as "<".
      std::string field = base::UTF16ToUTF8(text);
      base::ReplaceSubstringsAfterOffset(&field, 0, "&", "&amp;");
      fields.push_back(
          "q=" + base::EscapeQueryParamValue(field, /*use_plus=*/true));
    }

    auto request = std::make_unique<network::ResourceRequest>();
    request->url = url;
    request->method = "POST";
    request->credentials_mode = network::mojom::CredentialsMode::kOmit;
    std::unique_ptr<network::SimpleURLLoader> loader =
        network::SimpleURLLoader::Create(std::move(request),
                                         kGoogleTranslateAnnotation);
    loader->AttachStringForUpload(base::JoinString(fields, "&"),
                                  "application/x-www-form-urlencoded");
    network::SimpleURLLoader* raw_loader = loader.get();
    raw_loader->DownloadToString(
        loader_factory_.get(),
        base::BindOnce(&GoogleSession::OnReply, weak_factory_.GetWeakPtr(),
                       std::move(loader), texts.size(), source_lang,
                       target_lang, std::move(callback)),
        kMaxReplySize);
  }

 private:
  void OnReply(std::unique_ptr<network::SimpleURLLoader> loader,
               size_t count,
               const std::string& source_lang,
               const std::string& target_lang,
               TextsCallback callback,
               std::optional<std::string> reply) {
    if (!reply) {
      std::move(callback).Run(std::nullopt, source_lang,
                              TranslateErrors::NETWORK);
      return;
    }
    std::optional<base::Value> json =
        base::JSONReader::Read(*reply, base::JSON_PARSE_RFC);
    if (!json || !json->is_list() || json->GetList().size() != count) {
      std::move(callback).Run(std::nullopt, source_lang,
                              TranslateErrors::TRANSLATION_ERROR);
      return;
    }
    std::vector<std::u16string> translations;
    // Each text has its own detected language, and a short one, such as a
    // number, may be detected as the target language: the batch's is the
    // first that isn't.
    std::string detected;
    for (const base::Value& item : json->GetList()) {
      const base::Value* text = &item;
      // ["translation", "detected language"] when the source is "auto".
      if (item.is_list() && item.GetList().size() == 2 &&
          item.GetList()[1].is_string()) {
        const std::string& language = item.GetList()[1].GetString();
        if (detected.empty() || detected == target_lang) {
          detected = language;
        }
        text = &item.GetList()[0];
      }
      if (!text->is_string()) {
        std::move(callback).Run(std::nullopt, source_lang,
                                TranslateErrors::TRANSLATION_ERROR);
        return;
      }
      translations.push_back(base::UTF8ToUTF16(text->GetString()));
    }
    std::move(callback).Run(translations,
                            detected.empty() ? source_lang : detected,
                            TranslateErrors::NONE);
  }

  const scoped_refptr<network::SharedURLLoaderFactory> loader_factory_;
  base::WeakPtrFactory<GoogleSession> weak_factory_{this};
};

class GoogleProvider : public translate::TranslationProvider {
 public:
  bool IsAvailable() const override {
    return CurrentEngine() == Engine::kGoogle;
  }
  bool IsOnDevice() const override { return false; }
  // Unused: StartFrameSession starts this provider's sessions.
  std::unique_ptr<translate::TranslationSession> StartSession(
      const GURL& url) override {
    return std::make_unique<GoogleSession>(
        g_browser_process->shared_url_loader_factory());
  }
};

// The registered GoogleProvider, for StartFrameSession.
GoogleProvider* g_google_provider = nullptr;

std::unique_ptr<translate::TranslationSession> StartFrameSession(
    translate::TranslationProvider& provider,
    content::RenderFrameHost& frame) {
  if (&provider == g_google_provider) {
    return std::make_unique<GoogleSession>(
        frame.GetStoragePartition()->GetURLLoaderFactoryForBrowserProcess());
  }
  return provider.StartSession(frame.GetLastCommittedURL());
}

// TranslateKit's code for a Translate language code, or nullopt when it has
// no such language. As the service controller maps them.
std::optional<std::string> ToTranslateKitCode(std::string_view code) {
  std::string kit_code(code);
  if (kit_code == "he") {
    kit_code = "iw";
  } else if (kit_code == "zh-TW" || kit_code == "zh-HK") {
    kit_code = "zh-Hant";
  } else if (kit_code == "zh-CN") {
    kit_code = "zh";
  }
  return on_device_translation::LookupMatchingLocaleByBestFit(
      on_device_translation::kSupportedLanguageCodes, kit_code);
}

// The language packs a translation needs, or nullopt when TranslateKit lacks
// one of the languages.
std::optional<std::set<LanguagePackKey>> RequiredPacks(
    std::string_view source_lang,
    std::string_view target_lang) {
  const std::optional<std::string> source = ToTranslateKitCode(source_lang);
  const std::optional<std::string> target = ToTranslateKitCode(target_lang);
  if (!source || !target) {
    return std::nullopt;
  }
  return on_device_translation::CalculateRequiredLanguagePacks(*source,
                                                               *target);
}

std::set<LanguagePackKey> MissingPacks(
    const OnDeviceTranslationInstaller& installer,
    const std::set<LanguagePackKey>& required) {
  const std::set<LanguagePackKey> installed = installer.InstalledLanguagePacks();
  std::set<LanguagePackKey> missing;
  std::ranges::set_difference(required, installed,
                              std::inserter(missing, missing.end()));
  return missing;
}

// Whether TranslateKit's library is installed. Registering the component sets
// a relative path before it is.
bool LibraryReady(const OnDeviceTranslationInstaller& installer) {
  return installer.IsInit() && installer.GetLibraryPath().IsAbsolute();
}

// The downloads the user agreed to, and the translations waiting for them.
// A download that makes no progress for kGiveUpAfter is given up, so the
// next translation asks again.
class Downloads : public OnDeviceTranslationInstaller::Observer {
 public:
  static Downloads& Get() {
    static base::NoDestructor<Downloads> downloads;
    return *downloads;
  }

  bool Pending(LanguagePackKey pack) const { return pending_.contains(pack); }
  bool LibraryPending() const { return library_pending_; }

  // Downloads `packs`, and TranslateKit's library unless it is in.
  void Start(OnDeviceTranslationInstaller& installer,
             const std::set<LanguagePackKey>& packs) {
    if (!observation_.IsObserving()) {
      observation_.Observe(&installer);
    }
    component_updater::ComponentUpdateService* updater =
        g_browser_process->component_updater();
    const std::vector<std::string> registered = updater->GetComponentIDs();
    // A component registered earlier, at startup too, doesn't download on
    // registration: it is asked for.
    for (LanguagePackKey pack : packs) {
      pending_.insert(pack);
      const std::string id = crx_file::id_util::GenerateIdFromHash(
          on_device_translation::GetLanguagePackComponentConfig(pack)
              .public_key_sha);
      if (std::ranges::contains(registered, id)) {
        component_updater::TranslateKitLanguagePackComponentInstallerPolicy::
            UpdateComponentOnDemand(updater, pack);
      } else {
        installer.InstallLanguagePack(pack);
      }
    }
    if (!LibraryReady(installer)) {
      library_pending_ = true;
      if (std::ranges::contains(registered,
                         component_updater::
                             TranslateKitComponentInstallerPolicy::
                                 GetExtensionId())) {
        component_updater::TranslateKitComponentInstallerPolicy::
            UpdateComponentOnDemand(updater);
      } else {
        installer.Init(base::DoNothing());
      }
    }
    give_up_.Start(FROM_HERE, kGiveUpAfter,
                   base::BindOnce(&Downloads::GiveUp, base::Unretained(this)));
  }

  // Runs `translate` once `packs` and the library are installed.
  void Wait(std::set<LanguagePackKey> packs, base::OnceClosure translate) {
    waiters_.push_back({std::move(packs), std::move(translate)});
    Check();
  }

  // OnDeviceTranslationInstaller::Observer:
  void OnLanguagePackInstalled(LanguagePackKey pack) override { Check(); }
  void OnLanguagePackInstallationChanged(LanguagePackKey pack) override {
    Check();
  }
  void OnInstallationChanged() override { Check(); }

 private:
  friend class base::NoDestructor<Downloads>;
  Downloads() = default;

  static constexpr base::TimeDelta kGiveUpAfter = base::Minutes(10);

  struct Waiter {
    std::set<LanguagePackKey> packs;
    base::OnceClosure translate;
  };

  void Check() {
    OnDeviceTranslationInstaller* installer =
        OnDeviceTranslationInstaller::GetInstance();
    if (!installer) {
      return;
    }
    const std::set<LanguagePackKey> installed =
        installer->InstalledLanguagePacks();
    const size_t pending = pending_.size();
    std::erase_if(pending_, [&](LanguagePackKey pack) {
      return installed.contains(pack);
    });
    const bool library_ready = LibraryReady(*installer);
    if (library_ready && library_pending_) {
      library_pending_ = false;
    }
    if (pending_.size() != pending || library_ready) {
      // Progress: wait for the rest as long again.
      if (give_up_.IsRunning()) {
        give_up_.Reset();
      }
    }
    std::vector<base::OnceClosure> ready;
    std::erase_if(waiters_, [&](Waiter& waiter) {
      if (!library_ready || !std::ranges::includes(installed, waiter.packs)) {
        return false;
      }
      ready.push_back(std::move(waiter.translate));
      return true;
    });
    if (waiters_.empty() && pending_.empty() && !library_pending_) {
      give_up_.Stop();
      observation_.Reset();
    }
    for (base::OnceClosure& translate : ready) {
      std::move(translate).Run();
    }
  }

  void GiveUp() {
    pending_.clear();
    library_pending_ = false;
    waiters_.clear();
    observation_.Reset();
  }

  std::set<LanguagePackKey> pending_;
  bool library_pending_ = false;
  std::vector<Waiter> waiters_;
  base::OneShotTimer give_up_;
  base::ScopedObservation<OnDeviceTranslationInstaller,
                          OnDeviceTranslationInstaller::Observer>
      observation_{this};
};

// Translates with TranslateKit in Chromium's on-device translation service,
// one text at a time, with one translator for the session's language pair.
class OnDeviceSession : public translate::PlainTextTranslationSession {
 public:
  explicit OnDeviceSession(OnDeviceTranslationController& controller)
      : controller_(controller) {}

 protected:
  void TranslateTexts(const std::string& source_lang,
                      const std::string& target_lang,
                      std::vector<std::u16string> texts,
                      TextsCallback callback) override {
    // TranslateKit doesn't detect languages.
    if (source_lang == "auto" || source_lang == "und") {
      std::move(callback).Run(std::nullopt, source_lang,
                              TranslateErrors::UNKNOWN_LANGUAGE);
      return;
    }
    // Only with the packs in: the service controller would download missing
    // ones itself, and the user agrees to downloads first (ConfirmDownload).
    OnDeviceTranslationInstaller* installer =
        OnDeviceTranslationInstaller::GetInstance();
    const std::optional<std::set<LanguagePackKey>> required =
        RequiredPacks(source_lang, target_lang);
    if (!installer ||
        (required && !MissingPacks(*installer, *required).empty())) {
      std::move(callback).Run(std::nullopt, source_lang,
                              TranslateErrors::INITIALIZATION_ERROR);
      return;
    }
    auto job = std::make_unique<Job>();
    job->source_lang = source_lang;
    job->target_lang = target_lang;
    job->texts = std::move(texts);
    job->callback = std::move(callback);
    if (translator_.is_bound() && source_lang == translator_source_ &&
        target_lang == translator_target_) {
      TranslateNext(std::move(job));
      return;
    }
    waiting_.push_back(std::move(job));
    if (!creating_) {
      CreateTranslator(source_lang, target_lang);
    }
  }

 private:
  struct Job {
    std::string source_lang;
    std::string target_lang;
    std::vector<std::u16string> texts;
    std::vector<std::u16string> translations;
    TextsCallback callback;
  };

  void CreateTranslator(const std::string& source_lang,
                        const std::string& target_lang) {
    creating_ = true;
    translator_.reset();
    translator_source_ = source_lang;
    translator_target_ = target_lang;
    controller_->CreateTranslator(
        source_lang, target_lang,
        base::BindOnce(&OnDeviceSession::OnTranslatorCreated,
                       weak_factory_.GetWeakPtr()));
  }

  void OnTranslatorCreated(
      base::expected<
          mojo::PendingRemote<on_device_translation::mojom::OnDeviceTranslator>,
          OnDeviceTranslationController::CreateTranslatorError> result) {
    creating_ = false;
    std::vector<std::unique_ptr<Job>> waiting = std::move(waiting_);
    if (!result.has_value()) {
      const TranslateErrors error =
          result.error() == OnDeviceTranslationController::
                                CreateTranslatorError::kNotSupportedLanguage
              ? TranslateErrors::UNSUPPORTED_LANGUAGE
              : TranslateErrors::INITIALIZATION_ERROR;
      for (std::unique_ptr<Job>& job : waiting) {
        std::move(job->callback).Run(std::nullopt, job->source_lang, error);
      }
      return;
    }
    translator_.Bind(std::move(result.value()));
    translator_.reset_on_disconnect();
    for (std::unique_ptr<Job>& job : waiting) {
      // A job for another pair waits for its own translator.
      TranslateTexts(job->source_lang, job->target_lang, std::move(job->texts),
                     std::move(job->callback));
    }
  }

  void TranslateNext(std::unique_ptr<Job> job) {
    if (job->translations.size() == job->texts.size()) {
      std::move(job->callback).Run(job->translations, job->source_lang,
                                   TranslateErrors::NONE);
      return;
    }
    if (!translator_.is_bound()) {
      std::move(job->callback).Run(std::nullopt, job->source_lang,
                                   TranslateErrors::TRANSLATION_ERROR);
      return;
    }
    const std::string text =
        base::UTF16ToUTF8(job->texts[job->translations.size()]);
    translator_->Translate(
        text, mojo::WrapCallbackWithDefaultInvokeIfNotRun(
                  base::BindOnce(&OnDeviceSession::OnTranslated,
                                 weak_factory_.GetWeakPtr(), std::move(job)),
                  std::nullopt));
  }

  void OnTranslated(std::unique_ptr<Job> job,
                    const std::optional<std::string>& translation) {
    if (!translation) {
      std::move(job->callback).Run(std::nullopt, job->source_lang,
                                   TranslateErrors::TRANSLATION_ERROR);
      return;
    }
    job->translations.push_back(base::UTF8ToUTF16(*translation));
    TranslateNext(std::move(job));
  }

  const raw_ref<OnDeviceTranslationController> controller_;
  mojo::Remote<on_device_translation::mojom::OnDeviceTranslator> translator_;
  std::string translator_source_;
  std::string translator_target_;
  bool creating_ = false;
  // Jobs waiting for a translator.
  std::vector<std::unique_ptr<Job>> waiting_;
  base::WeakPtrFactory<OnDeviceSession> weak_factory_{this};
};

class OnDeviceProvider : public translate::TranslationProvider {
 public:
  bool IsAvailable() const override {
    return CurrentEngine() == Engine::kOnDevice &&
           OnDeviceTranslationInstaller::GetInstance();
  }
  bool IsOnDevice() const override { return true; }
  std::unique_ptr<translate::TranslationSession> StartSession(
      const GURL& url) override {
    // One service for every page, as the Translator API has one per origin.
    if (!controller_) {
      controller_ = std::make_unique<
          on_device_translation::OnDeviceTranslationServiceController>(
          on_device_translation::CreateOnDeviceTranslationServiceLauncher(),
          "translate", OnDeviceTranslationInstaller::GetInstance());
    }
    return std::make_unique<OnDeviceSession>(*controller_);
  }

 private:
  std::unique_ptr<on_device_translation::OnDeviceTranslationServiceController>
      controller_;
};

// The committed page of `web_contents`, to tell whether it is still there.
int PageId(content::WebContents& web_contents) {
  content::NavigationEntry* entry =
      web_contents.GetController().GetLastCommittedEntry();
  return entry ? entry->GetUniqueID() : 0;
}

void TranslateIfSamePage(base::WeakPtr<content::WebContents> web_contents,
                         int page_id,
                         base::OnceClosure translate) {
  if (web_contents && PageId(*web_contents) == page_id) {
    std::move(translate).Run();
  }
}

void OnDownloadAnswer(std::set<LanguagePackKey> to_download,
                      std::set<LanguagePackKey> required,
                      base::OnceClosure translate,
                      chrome::MessageBoxResult result) {
  OnDeviceTranslationInstaller* installer =
      OnDeviceTranslationInstaller::GetInstance();
  if (result != chrome::MESSAGE_BOX_RESULT_YES || !installer ||
      CurrentEngine() != Engine::kOnDevice) {
    return;
  }
  Downloads::Get().Start(*installer, to_download);
  Downloads::Get().Wait(std::move(required), std::move(translate));
}

}  // namespace

void RegisterProviders() {
  translate::RegisterTranslationProvider(std::make_unique<OnDeviceProvider>());
  auto google = std::make_unique<GoogleProvider>();
  g_google_provider = google.get();
  translate::RegisterTranslationProvider(std::move(google));
  translate::GetFrameSessionFactory() = base::BindRepeating(&StartFrameSession);
}

bool ConfirmDownload(content::WebContents* web_contents,
                     std::string_view source_lang,
                     std::string_view target_lang,
                     bool asked_by_user,
                     base::OnceClosure translate) {
  OnDeviceTranslationInstaller* installer =
      OnDeviceTranslationInstaller::GetInstance();
  if (CurrentEngine() != Engine::kOnDevice || !installer) {
    return true;
  }
  // Languages TranslateKit lacks fail in the session instead.
  const std::optional<std::set<LanguagePackKey>> required =
      RequiredPacks(source_lang, target_lang);
  if (!required) {
    return true;
  }
  const std::set<LanguagePackKey> missing = MissingPacks(*installer, *required);
  if (missing.empty() && LibraryReady(*installer)) {
    return true;
  }

  base::OnceClosure on_ready =
      base::BindOnce(&TranslateIfSamePage, web_contents->GetWeakPtr(),
                     PageId(*web_contents), std::move(translate));
  std::set<LanguagePackKey> to_ask;
  std::vector<std::u16string> names;
  const std::string& locale = g_browser_process->GetApplicationLocale();
  for (LanguagePackKey pack : missing) {
    if (Downloads::Get().Pending(pack)) {
      continue;
    }
    to_ask.insert(pack);
    const std::string_view language = on_device_translation::ToLanguageCode(
        on_device_translation::NonEnglishSupportedLanguageFromLanguagePackKey(
            pack));
    names.push_back(l10n_util::GetDisplayNameForLocale(
        std::string(language), locale, /*is_for_ui=*/true));
  }

  // Every missing pack downloads already, or none is missing and only the
  // library, which comes with the packs the user agreed to, isn't in.
  if (to_ask.empty()) {
    if (!LibraryReady(*installer) && !Downloads::Get().LibraryPending()) {
      Downloads::Get().Start(*installer, {});
    }
    Downloads::Get().Wait(*required, std::move(on_ready));
    return false;
  }
  // An automatic translation never starts a download.
  if (!asked_by_user) {
    return false;
  }
  chrome::ShowQuestionMessageBoxAsync(
      web_contents->GetTopLevelNativeWindow(),
      l10n_util::GetStringUTF16(IDS_OGANESSON_TRANSLATE_DOWNLOAD_TITLE),
      l10n_util::GetStringFUTF16(IDS_OGANESSON_TRANSLATE_DOWNLOAD_MESSAGE,
                                 base::JoinString(names, u", ")),
      base::BindOnce(&OnDownloadAnswer, std::move(to_ask), *required,
                     std::move(on_ready)));
  return false;
}

}  // namespace oganesson_translation
