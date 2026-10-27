// Copyright 2026 The oganesson Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/webui/prefs_editor/prefs_editor_ui.h"

#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/ref_counted_memory.h"
#include "base/values.h"
#include "chrome/browser/browser_process.h"
#include "chrome/browser/profiles/profile.h"
#include "components/prefs/pref_service.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "content/public/browser/web_ui_message_handler.h"

namespace {

// The page is plain HTML and script, served from here so it needs no
// build-time resources.
constexpr char kHtml[] = R"(<!doctype html>
<html dir="ltr" lang="en">
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="light dark">
<title>about:config</title>
<link rel="stylesheet" href="config.css">
<script type="module" src="config.js"></script>
</head>
<body>
<header>
  <h1>about:config</h1>
  <p id="warning">Changing these preferences can break oganesson or make it
  less secure. Most options have a page in Settings.</p>
  <input id="search" type="search" placeholder="Search preference name"
      aria-label="Search preference name" autofocus>
  <label><input id="changed" type="checkbox"> Only changed</label>
  <span id="count"></span>
</header>
<table>
  <thead><tr><th>Preference</th><th>Scope</th><th>Status</th><th>Type</th>
      <th>Value</th><th></th></tr></thead>
  <tbody id="prefs"></tbody>
</table>
</body>
</html>
)";

constexpr char kCss[] = R"(body { font-family: system-ui, sans-serif; margin: 0 16px; }
header { position: sticky; top: 0; background: Canvas; padding: 8px 0;
         display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
h1 { font-size: 1.2em; margin: 0; }
#warning { flex-basis: 100%; margin: 0; color: #b3261e; }
#search { flex: 1; min-width: 240px; padding: 4px 8px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: start; padding: 4px 6px; border-bottom: 1px solid #8884;
         vertical-align: top; }
td:first-child { font-family: monospace; word-break: break-all; }
tr.modified td:first-child { font-weight: bold; }
td.value input, td.value textarea { width: 100%; box-sizing: border-box;
                                    font-family: monospace; }
td.value textarea { min-height: 3em; }
.error { color: #b3261e; }
)";

constexpr char kJs[] = R"(// chrome://config. Talks to PrefsEditorHandler with chrome.send.
import {addWebUiListener, sendWithPromise} from 'chrome://resources/js/cr.js';

const $ = (id) => document.getElementById(id);
let prefs = [];

function editor(pref) {
  if (!pref.editable) {
    const span = document.createElement('span');
    span.textContent = pref.value;
    return span;
  }
  if (pref.type === 'boolean') {
    const button = document.createElement('button');
    button.textContent = pref.value;
    button.title = 'Toggle';
    button.onclick = () => save(pref, pref.value === 'true' ? 'false' : 'true');
    return button;
  }
  const multiline = pref.type === 'list' || pref.type === 'dictionary';
  const field = document.createElement(multiline ? 'textarea' : 'input');
  field.value = pref.type === 'string' ? JSON.parse(pref.value) : pref.value;
  field.setAttribute('aria-label', pref.name);
  field.onkeydown = (e) => {
    if (e.key === 'Enter' && (!multiline || e.ctrlKey)) {
      e.preventDefault();
      save(pref, pref.type === 'string' ? JSON.stringify(field.value) : field.value);
    }
  };
  field.title = multiline ? 'JSON; Ctrl+Enter saves' : 'Enter saves';
  return field;
}

function row(pref) {
  const tr = document.createElement('tr');
  tr.classList.toggle('modified', pref.status === 'user');
  tr.dataset.name = pref.name;
  for (const text of [pref.name, pref.scope, pref.status, pref.type]) {
    const td = document.createElement('td');
    td.textContent = text;
    tr.appendChild(td);
  }
  const value = document.createElement('td');
  value.className = 'value';
  value.appendChild(editor(pref));
  tr.appendChild(value);
  const actions = document.createElement('td');
  if (pref.editable && pref.status === 'user') {
    const reset = document.createElement('button');
    reset.textContent = 'Reset';
    reset.onclick = () => chrome.send('resetPref', [pref.scope, pref.name]);
    actions.appendChild(reset);
  }
  tr.appendChild(actions);
  return tr;
}

function render() {
  const query = $('search').value.trim().toLowerCase();
  const onlyChanged = $('changed').checked;
  const shown = prefs.filter((p) => p.name.toLowerCase().includes(query) &&
                                    (!onlyChanged || p.status === 'user'));
  $('prefs').replaceChildren(...shown.map(row));
  $('count').textContent = `${shown.length} of ${prefs.length}`;
}

async function save(pref, json) {
  const error = await sendWithPromise('setPref', pref.scope, pref.name, json);
  if (error) {
    alert(`${pref.name}: ${error}`);
  }
}

async function load() {
  prefs = (await sendWithPromise('getPrefs'))
      .sort((a, b) => a.name.localeCompare(b.name));
  render();
}

$('search').oninput = render;
$('changed').onchange = render;
addWebUiListener('prefs-changed', load);
window.addEventListener('focus', load);
load();
)";

// Lists and edits the profile's and the browser's (local state) prefs.
class PrefsEditorHandler : public content::WebUIMessageHandler {
 public:
  explicit PrefsEditorHandler(Profile* profile) : profile_(profile) {}

  void RegisterMessages() override {
    web_ui()->RegisterMessageCallback(
        "getPrefs", base::BindRepeating(&PrefsEditorHandler::GetPrefs,
                                        base::Unretained(this)));
    web_ui()->RegisterMessageCallback(
        "setPref", base::BindRepeating(&PrefsEditorHandler::SetPref,
                                       base::Unretained(this)));
    web_ui()->RegisterMessageCallback(
        "resetPref", base::BindRepeating(&PrefsEditorHandler::ResetPref,
                                         base::Unretained(this)));
  }

 private:
  PrefService* Prefs(std::string_view scope) {
    return scope == "browser" ? g_browser_process->local_state()
                              // Not an incognito window's, which forgets.
                              : profile_->GetOriginalProfile()->GetPrefs();
  }

  static const char* TypeName(base::Value::Type type) {
    switch (type) {
      case base::Value::Type::BOOLEAN:
        return "boolean";
      case base::Value::Type::INTEGER:
        return "integer";
      case base::Value::Type::DOUBLE:
        return "number";
      case base::Value::Type::STRING:
        return "string";
      case base::Value::Type::LIST:
        return "list";
      case base::Value::Type::DICT:
        return "dictionary";
      default:
        return "other";
    }
  }

  static const char* Status(const PrefService::Preference& pref) {
    if (pref.IsManaged() || pref.IsManagedByCustodian()) {
      return "managed";
    }
    if (pref.IsExtensionControlled()) {
      return "extension";
    }
    if (pref.IsRecommended()) {
      return "recommended";
    }
    return pref.IsDefaultValue() ? "default" : "user";
  }

  void AddPrefs(std::string_view scope, base::ListValue& out) {
    PrefService* prefs = Prefs(scope);
    std::vector<std::string> names;
    prefs->IteratePreferenceValues(base::BindRepeating(
        [](std::vector<std::string>* names, const std::string& key,
           const base::Value&) { names->push_back(key); },
        &names));
    for (const std::string& name : names) {
      const PrefService::Preference* pref = prefs->FindPreference(name);
      if (!pref) {
        continue;
      }
      out.Append(
          base::DictValue()
              .Set("name", name)
              .Set("scope", scope)
              .Set("type", TypeName(pref->GetType()))
              .Set("status", Status(*pref))
              .Set("editable", pref->IsUserModifiable())
              .Set("value", base::WriteJson(*pref->GetValue()).value_or("")));
    }
  }

  void GetPrefs(const base::ListValue& args) {
    AllowJavascript();
    base::ListValue out;
    AddPrefs("profile", out);
    AddPrefs("browser", out);
    ResolveJavascriptCallback(args[0], out);
  }

  // Sets a pref to a JSON value of its type. Resolves with an error message,
  // or "" on success.
  void SetPref(const base::ListValue& args) {
    AllowJavascript();
    const std::string* scope = args[1].GetIfString();
    const std::string* name = args[2].GetIfString();
    const std::string* json = args[3].GetIfString();
    PrefService* prefs = scope ? Prefs(*scope) : nullptr;
    const PrefService::Preference* pref =
        prefs && name ? prefs->FindPreference(*name) : nullptr;
    std::string error;
    std::optional<base::Value> value =
        json ? base::JSONReader::Read(*json, base::JSON_PARSE_RFC)
             : std::nullopt;
    if (!pref || !pref->IsUserModifiable()) {
      error = "This preference can't be changed.";
    } else if (!value) {
      error = "Not valid JSON.";
    } else if (value->type() != pref->GetType() &&
               !(pref->GetType() == base::Value::Type::DOUBLE &&
                 value->is_int())) {
      error = std::string("Expected a value of type ") +
              TypeName(pref->GetType()) + ".";
    } else {
      prefs->Set(*name, pref->GetType() == base::Value::Type::DOUBLE
                            ? base::Value(value->GetDouble())
                            : std::move(*value));
    }
    ResolveJavascriptCallback(args[0], base::Value(error));
    FireWebUIListener("prefs-changed");
  }

  void ResetPref(const base::ListValue& args) {
    AllowJavascript();
    const std::string* scope = args[0].GetIfString();
    const std::string* name = args[1].GetIfString();
    PrefService* prefs = scope ? Prefs(*scope) : nullptr;
    const PrefService::Preference* pref =
        prefs && name ? prefs->FindPreference(*name) : nullptr;
    if (pref && pref->IsUserModifiable()) {
      prefs->ClearPref(*name);
    }
    FireWebUIListener("prefs-changed");
  }

  const raw_ptr<Profile> profile_;
};

}  // namespace

PrefsEditorUI::PrefsEditorUI(content::WebUI* web_ui)
    : content::WebUIController(web_ui) {
  Profile* profile = Profile::FromWebUI(web_ui);
  content::WebUIDataSource* source = content::WebUIDataSource::CreateAndAdd(
      profile, kChromeUIPrefsEditorHost);
  source->SetRequestFilter(
      base::BindRepeating([](const std::string& path) {
        return path.empty() || path == "config.js" || path == "config.css";
      }),
      base::BindRepeating([](const std::string& path,
                             content::WebUIDataSource::GotDataCallback done) {
        std::string_view body = path == "config.js"    ? kJs
                                : path == "config.css" ? kCss
                                                       : kHtml;
        std::move(done).Run(
            base::MakeRefCounted<base::RefCountedString>(std::string(body)));
      }));
  web_ui->AddMessageHandler(std::make_unique<PrefsEditorHandler>(profile));
}

PrefsEditorUI::~PrefsEditorUI() = default;
