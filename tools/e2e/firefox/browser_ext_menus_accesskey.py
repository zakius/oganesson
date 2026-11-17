"""Port of Firefox's
browser/components/extensions/test/browser/browser_ext_menus_accesskey.js.

An item's access key is the character its title marks with `&`, which the
menu underlines (head.access_key()); an item without one has none. The
add-on's items are those of its submenu (getElementsByTagName("menuitem")
of openExtensionContextMenu()). Firefox's unified extensions panel is this
browser's Extensions menu, and an add-on's context menu there opens from its
row's More options button. SpecialPowers.spawn()'s selection runs in the
page. Left out: the items' `auto-accesskey` attribute and
`webextension-menuitem` class, Gecko's DOM, which tell where Firefox's
access key comes from and that another item may share it; the access key
itself is checked.
"""

from firefox import head
from extension_test_utils import JS

PAGE = f'{head.BASE}context.html'


class MenusAccesskeyTest(head.ContextMenuTest):

    def check_items(self, items, test_cases):
        """The test's checks of each item's label and access key."""
        self.is_(len(items), len(test_cases), 'Expected menu items for page')
        for i, (case, item) in enumerate(zip(test_cases, items)):
            description = case['description']
            self.is_(head.label_of(item), case['label'], f'Label for item {i} ({description})')
            self.is_(head.access_key(item), case.get('key', case.get('autoKey')),
                     f'Accesskey for item {i} ({description})')

    def test_01_accesskeys(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              // description is informative.
              // title is passed to menus.create.
              // label and key are compared with the actual values. autoKey
              // replaces key for an access key generated from the label.
              const TESTCASES = [
                {
                  description: "Amp at start",
                  title: "&accesskey",
                  label: "accesskey",
                  key: "a",
                },
                {
                  description: "amp in between",
                  title: "A& b",
                  label: "A b",
                  key: " ",
                },
                {
                  description: "lonely amp",
                  title: "&",
                  label: "",
                  autoKey: null,
                },
                {
                  description: "amp at end",
                  title: "End &",
                  label: "End ",
                  autoKey: "E",
                },
                {
                  description: "escaped amp",
                  title: "A && B",
                  label: "A & B",
                  autoKey: "A",
                },
                {
                  description: "amp before escaped amp",
                  title: "A &T&& before",
                  label: "A T& before",
                  key: "T",
                },
                {
                  description: "amp after escaped amp",
                  title: "A &&&T after",
                  label: "A &T after",
                  key: "T",
                },
                {
                  // Only the first amp should be used as the access key.
                  description: "amp, escaped amp, amp to ignore",
                  title: "First &1 comes && first &2 serves",
                  label: "First 1 comes & first 2 serves",
                  key: "1",
                },
                {
                  description: "no amp, leading punctuation",
                  title: '"Quoted" title',
                  label: '"Quoted" title',
                  autoKey: "Q",
                },
                {
                  description: "no amp, leading emoji",
                  title: "🦊 Fox",
                  label: "🦊 Fox",
                  autoKey: "F",
                },
                {
                  description: "no amp, leading digit",
                  title: "2 columns",
                  label: "2 columns",
                  autoKey: "2",
                },
                {
                  description: "no amp, Cyrillic",
                  title: "Перевести",
                  label: "Перевести",
                  autoKey: "П",
                },
                {
                  description: "no amp, letter outside the BMP",
                  title: "𞤀𞤣𞤤𞤢𞤥",
                  label: "𞤀𞤣𞤤𞤢𞤥",
                  autoKey: "𞤀",
                },
                {
                  description: "no amp, Chinese followed by Latin",
                  title: "翻译 English",
                  label: "翻译 English",
                  autoKey: "E",
                },
                {
                  description: "created with amp, updated without amp",
                  title: "temp with &X", // will be updated below.
                  label: "remove amp",
                  autoKey: "r",
                },
                {
                  description: "created without amp, update with amp",
                  title: "temp without access key", // will be updated below.
                  label: "add ampY",
                  key: "Y",
                },
              ];

              let menuIds = TESTCASES.map(({ title }) => browser.menus.create({ title }));

              // Should clear the access key:
              await browser.menus.update(menuIds[menuIds.length - 2], {
                title: "remove amp",
              });

              // Should add an access key:
              await browser.menus.update(menuIds[menuIds.length - 1], {
                title: "add amp&Y",
              });
              // Should not clear the access key because title is not set:
              await browser.menus.update(menuIds[menuIds.length - 1], { enabled: true });

              browser.test.sendMessage("testCases", TESTCASES);
            }'''))

        extension.startup()

        test_cases = extension.await_message('testCases')
        menu = head.open_extension_context_menu(self, tab)
        self.assertIsNotNone(menu, "the add-on's submenu")
        self.check_items(menu.items, test_cases)

        head.close_extension_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    def test_02_accesskeys_selection(self):
        page_with_amps = 'data:text/plain;charset=utf-8,PageSelection&Amp'
        tab = self.open_tab(page_with_amps)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              const TESTCASES = [
                {
                  description: "Selection without amp",
                  title: "percent-s: %s.",
                  label: "percent-s: PageSelection&Amp.",
                  autoKey: "p",
                },
                {
                  description: "Selection with amp after %s",
                  title: "percent-s: %s &A.",
                  label: "percent-s: PageSelection&Amp A.",
                  key: "A",
                },
                {
                  description: "Selection with amp before %s",
                  title: "percent-s: &B %s.",
                  label: "percent-s: B PageSelection&Amp.",
                  key: "B",
                },
                {
                  description: "Amp-percent",
                  title: "Amp-percent: &%.",
                  label: "Amp-percent: %.",
                  key: "%",
                },
                {
                  // "&%s" should be treated as "%s", and "ignore this" with amps should be ignored.
                  description: "Selection with amp-percent-s",
                  title: "Amp-percent-s: &%s.&i&g&n&o&r&e& &t&h&i&s",
                  label: "Amp-percent-s: PageSelection&Amp.ignore this",
                  // Chrome uses the first character of the selection as access key.
                  autoKey: "A",
                },
                {
                  description: "Selection with amp before amp-percent-s",
                  title: "Amp-percent-s: &_ &%s.",
                  label: "Amp-percent-s: _ PageSelection&Amp.",
                  key: "_",
                },
              ];

              let lastMenuId;
              for (let { title } of TESTCASES) {
                lastMenuId = browser.menus.create({ contexts: ["selection"], title });
              }
              // Round-trip to ensure that the menus have been registered.
              await browser.menus.update(lastMenuId, {});
              browser.test.sendMessage("testCases", TESTCASES);
            }'''))

        extension.startup()

        # Select all
        tab.eval('''(() => {
          let doc = document;
          let range = doc.createRange();
          let selection = getSelection();
          selection.removeAllRanges();
          range.selectNodeContents(doc.body);
          selection.addRange(range);
        })()''')

        test_cases = extension.await_message('testCases')
        menu = head.open_extension_context_menu(self, tab)
        self.assertIsNotNone(menu, "the add-on's submenu")
        self.check_items(menu.items, test_cases)

        head.close_extension_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    def check_access_keys_in_extension_menu(self, test_cases):
        """checkAccessKeysInExtensionMenu()."""
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.test.onMessage.addListener(async titles => {
                let lastMenuId;
                for (let title of titles) {
                  lastMenuId = browser.menus.create({ title });
                }
                // Round-trip to ensure that the menus have been registered.
                await browser.menus.update(lastMenuId, {});
                browser.test.sendMessage("created");
              });
            }'''))

        extension.startup()
        extension.send_message([case['title'] for case in test_cases])
        extension.await_message('created')

        menu = head.open_extension_context_menu(self, tab)
        self.assertIsNotNone(menu, "the add-on's submenu")
        self.is_(len(menu.items), len(test_cases), 'Expected menu items for page')
        for case, item in zip(test_cases, menu.items):
            self.is_(head.access_key(item), case.get('key', case.get('autoKey')),
                     f'Accesskey for "{case["title"]}"')

        head.close_extension_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    # A letter typed through an IME can't be an access key, so these items get
    # digits instead.
    def test_03_accesskeys_ime_scripts(self):
        self.check_access_keys_in_extension_menu([
            {'title': '翻译', 'autoKey': '1'},
            {'title': 'ひらがなカタカナ', 'autoKey': '2'},
            {'title': '번역', 'autoKey': '3'},
            {'title': 'ＰＤＦで保存', 'autoKey': '4'},
            {'title': 'ページを２倍', 'autoKey': '5'},
        ])

    def test_04_accesskeys_ime_scripts_mixed(self):
        self.check_access_keys_in_extension_menu([
            {'title': '&Copy', 'key': 'C'},
            {'title': '翻译', 'autoKey': '1'},
            {'title': '2 columns', 'autoKey': '2'},
            {'title': '🦊', 'autoKey': '3'},
            {'title': 'Paste', 'autoKey': 'P'},
        ])

    def test_05_accesskeys_top_level_menu(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.create({ id: "parent", title: "Parent", contexts: ["all"] });
              browser.menus.create({ parentId: "parent", title: "Child" });
              // Round-trip to ensure that the menus have been registered.
              await browser.menus.update("parent", {});
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')

        context_menu = head.open_context_menu(self, tab, '#img1')
        # The add-on's one item, a submenu.
        menu = context_menu.by_label('Parent')
        self.assertTrue(menu, "the menu has the add-on's item")
        self.is_(head.has_submenu(self, menu[0]), True, "The extension's item is a submenu")
        self.is_(head.access_key(menu[0]), 'P', 'A submenu gets an accesskey')

        head.close_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    def test_06_accesskeys_refresh_while_open(self):
        tab = self.open_tab(PAGE)

        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
            },
            background=JS('''async function background() {
              browser.menus.onShown.addListener(async () => {
                await browser.menus.update("item", { title: "Changed" });
                await browser.menus.refresh();
                browser.test.sendMessage("refreshed");
              });
              browser.menus.create({ id: "item", title: "Before", contexts: ["all"] });
              // Round-trip to ensure that the menus have been registered.
              await browser.menus.update("item", {});
              browser.test.sendMessage("ready");
            }'''))

        extension.startup()
        extension.await_message('ready')

        head.open_context_menu(self, tab, '#img1')
        extension.await_message('refreshed')
        # The open menu, read again.
        context_menu = head.first_menu(self)
        item = context_menu.by_label('Changed')
        self.assertTrue(item, 'The item was rebuilt while the menu is open')
        self.is_(head.access_key(item[0]), 'C', 'The rebuilt item gets an accesskey')

        head.close_context_menu(self)
        extension.unload()
        self.browser.close_target(tab)

    # The unified extensions context menu gives its own items no accesskeys, so an
    # extension's item gets none either and doesn't take the first letter of
    # "Manage Extension".
    def test_07_accesskeys_menu_without_accesskeys(self):
        extension = self.load_extension(
            manifest={
                'permissions': ['menus'],
                'browser_action': {'default_area': 'menupanel'},
            },
            background=JS('''async function background() {
              browser.menus.create({
                id: "item",
                title: "Manage tabs",
                contexts: ["browser_action"],
              });
              // Round-trip to ensure that the menus have been registered.
              await browser.menus.update("item", {});
              browser.test.sendMessage("ready");
            }'''),
            use_addon_manager='temporary')

        extension.startup()
        extension.await_message('ready')

        head.open_extensions_panel(self)
        menu = head.open_unified_extensions_context_menu(self)
        item = menu.by_label('Manage tabs')
        self.assertTrue(item, "The extension's item is in the menu")
        self.is_(head.access_key(item[0]), None, "The extension's item gets no accesskey")

        head.close_context_menu(self)
        head.close_extensions_panel(self)
        extension.unload()
