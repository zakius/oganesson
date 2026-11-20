"""Firefox's toolkit/components/extensions/test/xpcshell/head_storage.js:
the storage tests that its test files run on more than one storage area. The
add-ons' code is Firefox's, as it is; each function takes the FirefoxTest that
runs it. Only the functions that a port runs are here.

Left out of test_storage_change_event_page: assertPersistentListeners(),
which reads Gecko's primed listeners. Its terminateBackground() needs the
test class's EVENT_PAGE_ARGS.

As in Firefox, test_contentscript_storage() and
test_contentscript_storage_area_getBytesInUse() open their content page
before the add-on starts, and Firefox runs the add-on's content script in
it."""

import json

from extension_test_utils import JS

CHECK_GET_IMPL = r'''async function checkGetImpl(areaName, prop, value) {
  let storage = browser.storage[areaName];

  let data = await storage.get();
  browser.test.assertEq(
    value,
    data[prop],
    `unspecified getter worked for ${prop} in ${areaName}`
  );

  data = await storage.get(null);
  browser.test.assertEq(
    value,
    data[prop],
    `null getter worked for ${prop} in ${areaName}`
  );

  data = await storage.get(prop);
  browser.test.assertEq(
    value,
    data[prop],
    `string getter worked for ${prop} in ${areaName}`
  );
  browser.test.assertEq(
    Object.keys(data).length,
    1,
    `string getter should return an object with a single property`
  );

  data = await storage.get([prop]);
  browser.test.assertEq(
    value,
    data[prop],
    `array getter worked for ${prop} in ${areaName}`
  );
  browser.test.assertEq(
    Object.keys(data).length,
    1,
    `array getter with a single key should return an object with a single property`
  );

  data = await storage.get({ [prop]: undefined });
  browser.test.assertEq(
    value,
    data[prop],
    `object getter worked for ${prop} in ${areaName}`
  );
  browser.test.assertEq(
    Object.keys(data).length,
    1,
    `object getter with a single key should return an object with a single property`
  );
}'''

AFTER_RELOAD_BACKGROUND = r'''async function background(areaName) {
  browser.test.sendMessage(
    "initialItems",
    await browser.storage[areaName].get(null)
  );
  await browser.storage[areaName].set({ a: "b" });
  browser.test.notifyPass("set-works");
}'''

PAGE_STORAGE_BACKGROUND = r'''async function backgroundScript(checkGet) {
  let globalChanges, gResolve;
  function clearGlobalChanges() {
    globalChanges = new Promise(resolve => {
      gResolve = resolve;
    });
  }
  clearGlobalChanges();
  let expectedAreaName;

  browser.storage.onChanged.addListener((changes, areaName) => {
    browser.test.assertEq(
      expectedAreaName,
      areaName,
      "Expected area name received by listener"
    );
    gResolve(changes);
  });

  async function checkChanges(areaName, changes, message) {
    function checkSub(obj1, obj2) {
      for (let prop in obj1) {
        browser.test.assertTrue(
          obj1[prop] !== undefined,
          `checkChanges ${areaName} ${prop} is missing (${message})`
        );
        browser.test.assertTrue(
          obj2[prop] !== undefined,
          `checkChanges ${areaName} ${prop} is missing (${message})`
        );
        browser.test.assertEq(
          obj1[prop].oldValue,
          obj2[prop].oldValue,
          `checkChanges ${areaName} ${prop} old (${message})`
        );
        browser.test.assertEq(
          obj1[prop].newValue,
          obj2[prop].newValue,
          `checkChanges ${areaName} ${prop} new (${message})`
        );
      }
    }

    const recentChanges = await globalChanges;
    checkSub(changes, recentChanges);
    checkSub(recentChanges, changes);
    clearGlobalChanges();
  }

  // Regression test for https://bugzilla.mozilla.org/show_bug.cgi?id=1645598
  async function testNonExistingKeys(storage, storageAreaDesc) {
    let data = await storage.get({ test6: 6 });
    browser.test.assertEq(
      `{"test6":6}`,
      JSON.stringify(data),
      `Use default value when not stored for ${storageAreaDesc}`
    );

    data = await storage.get({ test6: null });
    browser.test.assertEq(
      `{"test6":null}`,
      JSON.stringify(data),
      `Use default value, even if null for ${storageAreaDesc}`
    );

    data = await storage.get("test6");
    browser.test.assertEq(
      `{}`,
      JSON.stringify(data),
      `Empty result if key is not found for ${storageAreaDesc}`
    );

    data = await storage.get(["test6", "test7"]);
    browser.test.assertEq(
      `{}`,
      JSON.stringify(data),
      `Empty result if list of keys is not found for ${storageAreaDesc}`
    );
  }

  // Regression test https://bugzilla.mozilla.org/show_bug.cgi?id=1989840
  async function testDeeplyNestedObject(areaName) {
    const obj = {};
    let current = obj;
    for (let i = 0; i < 127; i++) {
      const next = {};
      current.foo = next;
      current = next;
    }
    let storage = browser.storage[areaName];
    if (areaName == "sync") {
      // TODO(bug 1990313)
      // Storing a deeply nested object currently fails for the Rust sync storage, but not Kinto.
      // Let's make sure it doesn't crash in any case.
      let errorMessage = null;
      try {
        await storage.set(obj);
      } catch (e) {
        errorMessage = e.toString();
        // The caller expects one storage event. To make sure that the event is
        // fired, trigger a dummy change.
        storage.set({ foo: "dummy" });
      }
      browser.test.assertTrue(
        errorMessage === null ||
          errorMessage.includes("An unexpected error occurred"),
        `Invalid exception message when storing deeply nested object: ${errorMessage}`
      );
    } else {
      // Storing a deeply nested object should succeed for non-sync engines.
      await storage.set(obj);
    }
  }

  async function testFalseyValues(areaName) {
    let storage = browser.storage[areaName];
    const dataInitial = {
      "test-falsey-value-bool": false,
      "test-falsey-value-string": "",
      "test-falsey-value-number": 0,
    };
    const dataUpdate = {
      "test-falsey-value-bool": true,
      "test-falsey-value-string": "non-empty-string",
      "test-falsey-value-number": 10,
    };

    // Compute the expected changes.
    const onSetInitial = {
      "test-falsey-value-bool": { newValue: false },
      "test-falsey-value-string": { newValue: "" },
      "test-falsey-value-number": { newValue: 0 },
    };
    const onRemovedFalsey = {
      "test-falsey-value-bool": { oldValue: false },
      "test-falsey-value-string": { oldValue: "" },
      "test-falsey-value-number": { oldValue: 0 },
    };
    const onUpdatedFalsey = {
      "test-falsey-value-bool": { newValue: true, oldValue: false },
      "test-falsey-value-string": {
        newValue: "non-empty-string",
        oldValue: "",
      },
      "test-falsey-value-number": { newValue: 10, oldValue: 0 },
    };
    const keys = Object.keys(dataInitial);

    // Test on removing falsey values.
    await storage.set(dataInitial);
    await checkChanges(areaName, onSetInitial, "set falsey values");
    await storage.remove(keys);
    await checkChanges(areaName, onRemovedFalsey, "remove falsey value");

    // Test on updating falsey values.
    await storage.set(dataInitial);
    await checkChanges(areaName, onSetInitial, "set falsey values");
    await storage.set(dataUpdate);
    await checkChanges(areaName, onUpdatedFalsey, "set non-falsey values");

    // Clear the storage state.
    await testNonExistingKeys(storage, `${areaName} before clearing`);
    await storage.clear();
    await testNonExistingKeys(storage, `${areaName} after clearing`);
    await globalChanges;
    clearGlobalChanges();
  }

  function CustomObj() {
    this.testKey1 = "testValue1";
  }

  CustomObj.prototype.toString = function () {
    return '{"testKey2":"testValue2"}';
  };

  CustomObj.prototype.toJSON = function customObjToJSON() {
    return { testKey1: "testValue3" };
  };

  /* eslint-disable dot-notation */
  async function runTests(areaName) {
    expectedAreaName = areaName;
    let storage = browser.storage[areaName];
    // Set some data and then test getters.
    try {
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });
      await checkChanges(
        areaName,
        {
          "test-prop1": { newValue: "value1" },
          "test-prop2": { newValue: "value2" },
        },
        "set (a)"
      );

      await checkGet(areaName, "test-prop1", "value1");
      await checkGet(areaName, "test-prop2", "value2");

      let data = await storage.get({
        "test-prop1": undefined,
        "test-prop2": undefined,
        other: "default",
      });
      browser.test.assertEq(
        "value1",
        data["test-prop1"],
        "prop1 correct (a)"
      );
      browser.test.assertEq(
        "value2",
        data["test-prop2"],
        "prop2 correct (a)"
      );
      browser.test.assertEq("default", data["other"], "other correct");

      data = await storage.get(["test-prop1", "test-prop2", "other"]);
      browser.test.assertEq(
        "value1",
        data["test-prop1"],
        "prop1 correct (b)"
      );
      browser.test.assertEq(
        "value2",
        data["test-prop2"],
        "prop2 correct (b)"
      );
      browser.test.assertFalse("other" in data, "other correct");

      // Remove data in various ways.
      await storage.remove("test-prop1");
      await checkChanges(
        areaName,
        { "test-prop1": { oldValue: "value1" } },
        "remove string"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse(
        "test-prop1" in data,
        "prop1 absent (remove string)"
      );
      browser.test.assertTrue(
        "test-prop2" in data,
        "prop2 present (remove string)"
      );

      await storage.set({ "test-prop1": "value1" });
      await checkChanges(
        areaName,
        { "test-prop1": { newValue: "value1" } },
        "set (c)"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertEq(
        data["test-prop1"],
        "value1",
        "prop1 correct (c)"
      );
      browser.test.assertEq(
        data["test-prop2"],
        "value2",
        "prop2 correct (c)"
      );

      await storage.remove(["test-prop1", "test-prop2"]);
      await checkChanges(
        areaName,
        {
          "test-prop1": { oldValue: "value1" },
          "test-prop2": { oldValue: "value2" },
        },
        "remove array"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse(
        "test-prop1" in data,
        "prop1 absent (remove array)"
      );
      browser.test.assertFalse(
        "test-prop2" in data,
        "prop2 absent (remove array)"
      );

      await testFalseyValues(areaName);

      // test storage.clear
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });
      // Make sure that set() handler happened before we clear the
      // promise again.
      await globalChanges;

      clearGlobalChanges();
      await storage.clear();

      await checkChanges(
        areaName,
        {
          "test-prop1": { oldValue: "value1" },
          "test-prop2": { oldValue: "value2" },
        },
        "clear"
      );
      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse("test-prop1" in data, "prop1 absent (clear)");
      browser.test.assertFalse("test-prop2" in data, "prop2 absent (clear)");

      // Make sure we can store complex JSON data.
      // known previous values
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });

      // Make sure the set() handler landed.
      await globalChanges;

      let date = new Date(0);

      clearGlobalChanges();
      await storage.set({
        "test-prop1": {
          str: "hello",
          bool: true,
          null: null,
          undef: undefined,
          obj: {},
          nestedObj: {
            testKey: {},
          },
          intKeyObj: {
            4: "testValue1",
            3: "testValue2",
            99: "testValue3",
          },
          floatKeyObj: {
            1.4: "testValue1",
            5.5: "testValue2",
          },
          customObj: new CustomObj(),
          arr: [1, 2],
          nestedArr: [1, [2, 3]],
          date,
          regexp: /regexp/,
        },
      });

      await browser.test.assertRejects(
        storage.set({
          window,
        }),
        /DataCloneError|cyclic object value/
      );

      await browser.test.assertRejects(
        storage.set({ "test-prop2": function func() {} }),
        /DataCloneError/
      );

      const recentChanges = await globalChanges;

      browser.test.assertEq(
        "value1",
        recentChanges["test-prop1"].oldValue,
        "oldValue correct"
      );
      browser.test.assertEq(
        "object",
        typeof recentChanges["test-prop1"].newValue,
        "newValue is obj"
      );
      clearGlobalChanges();

      data = await storage.get({
        "test-prop1": undefined,
        "test-prop2": undefined,
      });
      let obj = data["test-prop1"];

      browser.test.assertEq(
        "object",
        typeof obj.customObj,
        "custom object part correct"
      );
      browser.test.assertEq(
        1,
        Object.keys(obj.customObj).length,
        "customObj keys correct"
      );

      if (areaName === "local" || areaName === "session") {
        browser.test.assertEq(
          String(date),
          String(obj.date),
          "date part correct"
        );
        browser.test.assertEq(
          "/regexp/",
          obj.regexp.toString(),
          "regexp part correct"
        );
        // storage.local and .session don't use toJSON().
        browser.test.assertEq(
          "testValue1",
          obj.customObj.testKey1,
          "customObj keys correct"
        );
      } else {
        browser.test.assertEq(
          "1970-01-01T00:00:00.000Z",
          String(obj.date),
          "date part correct"
        );

        browser.test.assertEq(
          "object",
          typeof obj.regexp,
          "regexp part is an object"
        );
        browser.test.assertEq(
          0,
          Object.keys(obj.regexp).length,
          "regexp part is an empty object"
        );
        // storage.sync does call toJSON
        browser.test.assertEq(
          "testValue3",
          obj.customObj.testKey1,
          "customObj keys correct"
        );
      }

      browser.test.assertEq("hello", obj.str, "string part correct");
      browser.test.assertEq(true, obj.bool, "bool part correct");
      browser.test.assertEq(null, obj.null, "null part correct");
      browser.test.assertEq(undefined, obj.undef, "undefined part correct");
      browser.test.assertEq(undefined, obj.window, "window part correct");
      browser.test.assertEq("object", typeof obj.obj, "object part correct");
      browser.test.assertEq(
        "object",
        typeof obj.nestedObj,
        "nested object part correct"
      );
      browser.test.assertEq(
        "object",
        typeof obj.nestedObj.testKey,
        "nestedObj.testKey part correct"
      );
      browser.test.assertEq(
        "object",
        typeof obj.intKeyObj,
        "int key object part correct"
      );
      browser.test.assertEq(
        "testValue1",
        obj.intKeyObj[4],
        "intKeyObj[4] part correct"
      );
      browser.test.assertEq(
        "testValue2",
        obj.intKeyObj[3],
        "intKeyObj[3] part correct"
      );
      browser.test.assertEq(
        "testValue3",
        obj.intKeyObj[99],
        "intKeyObj[99] part correct"
      );
      browser.test.assertEq(
        "object",
        typeof obj.floatKeyObj,
        "float key object part correct"
      );
      browser.test.assertEq(
        "testValue1",
        obj.floatKeyObj[1.4],
        "floatKeyObj[1.4] part correct"
      );
      browser.test.assertEq(
        "testValue2",
        obj.floatKeyObj[5.5],
        "floatKeyObj[5.5] part correct"
      );

      browser.test.assertTrue(Array.isArray(obj.arr), "array part present");
      browser.test.assertEq(1, obj.arr[0], "arr[0] part correct");
      browser.test.assertEq(2, obj.arr[1], "arr[1] part correct");
      browser.test.assertEq(2, obj.arr.length, "arr.length part correct");
      browser.test.assertTrue(
        Array.isArray(obj.nestedArr),
        "nested array part present"
      );
      browser.test.assertEq(
        2,
        obj.nestedArr.length,
        "nestedArr.length part correct"
      );
      browser.test.assertEq(1, obj.nestedArr[0], "nestedArr[0] part correct");
      browser.test.assertTrue(
        Array.isArray(obj.nestedArr[1]),
        "nestedArr[1] part present"
      );
      browser.test.assertEq(
        2,
        obj.nestedArr[1].length,
        "nestedArr[1].length part correct"
      );
      browser.test.assertEq(
        2,
        obj.nestedArr[1][0],
        "nestedArr[1][0] part correct"
      );
      browser.test.assertEq(
        3,
        obj.nestedArr[1][1],
        "nestedArr[1][1] part correct"
      );

      // test storage.getKeys()
      clearGlobalChanges();
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });
      await globalChanges;
      const keys = await storage.getKeys();
      browser.test.assertDeepEq(
        keys,
        ["test-prop1", "test-prop2"],
        "getKeys() returns the correct keys"
      );
      clearGlobalChanges();
      await storage.clear();
      await globalChanges;

      clearGlobalChanges();
      await testDeeplyNestedObject(areaName);
      await globalChanges;
      clearGlobalChanges();
      await storage.clear();
      await globalChanges;
    } catch (e) {
      browser.test.fail(`Error: ${e} :: ${e.stack}`);
      browser.test.notifyFail("storage");
    }
  }

  browser.test.onMessage.addListener(msg => {
    let promise;
    if (msg === "test-local") {
      promise = runTests("local");
    } else if (msg === "test-sync") {
      promise = runTests("sync");
    } else if (msg === "test-session") {
      promise = runTests("session");
    }
    promise.then(() => browser.test.sendMessage("test-finished"));
  });

  browser.test.sendMessage("ready");
}'''

EMPTY_EVENTS_BACKGROUND = r'''async function background(areaName) {
  let eventCount = 0;

  browser.storage[areaName].onChanged.addListener(changes => {
    browser.test.sendMessage("onChanged", [++eventCount, changes]);
  });

  browser.test.onMessage.addListener(async (method, arg) => {
    let result = await browser.storage[areaName][method](arg);
    browser.test.sendMessage("result", result);
  });

  browser.test.sendMessage("ready");
}'''

ON_CHANGED_TOP_NAMESPACE = r'''function backgroundTestStorageTopNamespace(areaName) {
  browser.storage.onChanged.addListener((changes, area) => {
    browser.test.assertEq(area, areaName, "Expected areaName");
    browser.test.assertEq(
      JSON.stringify(changes),
      `{"storageKey":{"newValue":"newStorageValue"}}`,
      "Expected changes"
    );
    browser.test.sendMessage("onChanged_was_fired");
  });
}'''

ON_CHANGED_AREA_NAMESPACE = r'''function backgroundTestStorageAreaNamespace(areaName) {
  browser.storage[areaName].onChanged.addListener((changes, ...args) => {
    browser.test.assertEq(args.length, 0, "no more args after changes");
    browser.test.assertEq(
      JSON.stringify(changes),
      `{"storageKey":{"newValue":"newStorageValue"}}`,
      `Expected changes via ${areaName}.onChanged event`
    );
    browser.test.sendMessage("onChanged_was_fired");
  });
}'''

TRIGGER_CHANGE = r'''async () => {
  let areaName = location.search.slice(1);
  await browser.storage[areaName].set({
    storageKey: "newStorageValue",
  });
  browser.test.sendMessage("tried_to_trigger_change");
}'''

CHECK_GET_BYTES_IN_USE = r'''async function check_get_bytes_in_use(areaName, idbBackend) {
  const storage = browser.storage[areaName];
  let expectedKey = areaName;
  if (areaName === "local") {
    expectedKey += idbBackend ? "-idb" : "-json";
  }
  const tests = [
    {
      key: null,
      expected: {
        "local-json": 118,
        "local-idb": 228,
        session: 228,
        sync: 118,
      },
      message: "getBytesInUse(null) returns correct value for storage",
    },
    {
      key: "key2",
      expected: { "local-json": 23, "local-idb": 60, session: 60, sync: 23 },
      message: "getBytesInUse() returns correct value for a single key",
    },
    {
      key: "foo",
      expected: { "local-json": 0, "local-idb": 0, session: 0, sync: 0 },
      message: "getBytesInUse() returns 0 for a key not in storage",
    },
    {
      key: [],
      expected: { "local-json": 0, "local-idb": 0, session: 0, sync: 0 },
      message: "getBytesInUse() returns 0 for an empty array of keys",
    },
    {
      key: ["key1", "key3"],
      expected: { "local-json": 21, "local-idb": 48, session: 48, sync: 21 },
      message: "getBytesInUse() returns correct value for an array of keys",
    },
    {
      key: "",
      expected: { "local-json": 39, "local-idb": 56, session: 56, sync: 39 },
      message:
        'getBytesInUse() returns correct value for an empty string key ("")',
    },
  ];

  try {
    browser.test.assertEq(
      0,
      await storage.getBytesInUse(),
      "getBytesInUse() returns 0 when storage is empty"
    );

    await storage.set({
      key1: "value1",
      key2: { nested: "value2" },
      key3: 12345,
      key4: "Привет, мир!",
      null: null,
      "": "Value for key that's an empty string.",
    });

    for (let test of tests) {
      browser.test.assertEq(
        test.expected[expectedKey],
        await storage.getBytesInUse(test.key),
        test.message
      );
    }
  } catch (e) {
    browser.test.fail(`Error: ${e} :: ${e.stack}`);
    browser.test.notifyFail("storage");
  }

  browser.test.sendMessage("test-finished");
}'''


STORAGE_CONTENT_SCRIPT = r'''async function testStorageContentScript(checkGet) {
  let globalChanges, gResolve;
  function clearGlobalChanges() {
    globalChanges = new Promise(resolve => {
      gResolve = resolve;
    });
  }
  clearGlobalChanges();
  let expectedAreaName;

  browser.storage.onChanged.addListener((changes, areaName) => {
    browser.test.assertEq(
      expectedAreaName,
      areaName,
      "Expected area name received by listener"
    );
    gResolve(changes);
  });

  async function checkChanges(areaName, changes, message) {
    function checkSub(obj1, obj2) {
      for (let prop in obj1) {
        browser.test.assertTrue(
          obj1[prop] !== undefined,
          `checkChanges ${areaName} ${prop} is missing (${message})`
        );
        browser.test.assertTrue(
          obj2[prop] !== undefined,
          `checkChanges ${areaName} ${prop} is missing (${message})`
        );
        browser.test.assertEq(
          obj1[prop].oldValue,
          obj2[prop].oldValue,
          `checkChanges ${areaName} ${prop} old (${message})`
        );
        browser.test.assertEq(
          obj1[prop].newValue,
          obj2[prop].newValue,
          `checkChanges ${areaName} ${prop} new (${message})`
        );
      }
    }

    const recentChanges = await globalChanges;
    checkSub(changes, recentChanges);
    checkSub(recentChanges, changes);
    clearGlobalChanges();
  }

  /* eslint-disable dot-notation */
  async function runTests(areaName) {
    expectedAreaName = areaName;
    let storage = browser.storage[areaName];
    // Set some data and then test getters.
    try {
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });
      await checkChanges(
        areaName,
        {
          "test-prop1": { newValue: "value1" },
          "test-prop2": { newValue: "value2" },
        },
        "set (a)"
      );

      await checkGet(areaName, "test-prop1", "value1");
      await checkGet(areaName, "test-prop2", "value2");

      let data = await storage.get({
        "test-prop1": undefined,
        "test-prop2": undefined,
        other: "default",
      });
      browser.test.assertEq("value1", data["test-prop1"], "prop1 correct (a)");
      browser.test.assertEq("value2", data["test-prop2"], "prop2 correct (a)");
      browser.test.assertEq("default", data["other"], "other correct");

      data = await storage.get(["test-prop1", "test-prop2", "other"]);
      browser.test.assertEq("value1", data["test-prop1"], "prop1 correct (b)");
      browser.test.assertEq("value2", data["test-prop2"], "prop2 correct (b)");
      browser.test.assertFalse("other" in data, "other correct");

      // Remove data in various ways.
      await storage.remove("test-prop1");
      await checkChanges(
        areaName,
        { "test-prop1": { oldValue: "value1" } },
        "remove string"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse(
        "test-prop1" in data,
        "prop1 absent (remove string)"
      );
      browser.test.assertTrue(
        "test-prop2" in data,
        "prop2 present (remove string)"
      );

      await storage.set({ "test-prop1": "value1" });
      await checkChanges(
        areaName,
        { "test-prop1": { newValue: "value1" } },
        "set (c)"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertEq(data["test-prop1"], "value1", "prop1 correct (c)");
      browser.test.assertEq(data["test-prop2"], "value2", "prop2 correct (c)");

      await storage.remove(["test-prop1", "test-prop2"]);
      await checkChanges(
        areaName,
        {
          "test-prop1": { oldValue: "value1" },
          "test-prop2": { oldValue: "value2" },
        },
        "remove array"
      );

      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse(
        "test-prop1" in data,
        "prop1 absent (remove array)"
      );
      browser.test.assertFalse(
        "test-prop2" in data,
        "prop2 absent (remove array)"
      );

      // test storage.clear
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });
      // Make sure that set() handler happened before we clear the
      // promise again.
      await globalChanges;

      clearGlobalChanges();
      await storage.clear();

      await checkChanges(
        areaName,
        {
          "test-prop1": { oldValue: "value1" },
          "test-prop2": { oldValue: "value2" },
        },
        "clear"
      );
      data = await storage.get(["test-prop1", "test-prop2"]);
      browser.test.assertFalse("test-prop1" in data, "prop1 absent (clear)");
      browser.test.assertFalse("test-prop2" in data, "prop2 absent (clear)");

      // Make sure we can store complex JSON data.
      // known previous values
      await storage.set({ "test-prop1": "value1", "test-prop2": "value2" });

      // Make sure the set() handler landed.
      await globalChanges;

      let date = new Date(0);

      clearGlobalChanges();
      await storage.set({
        "test-prop1": {
          str: "hello",
          bool: true,
          null: null,
          undef: undefined,
          obj: {},
          arr: [1, 2],
          date: new Date(0),
          regexp: /regexp/,
        },
      });

      await browser.test.assertRejects(
        storage.set({
          window,
        }),
        /DataCloneError|cyclic object value/
      );

      await browser.test.assertRejects(
        storage.set({ "test-prop2": function func() {} }),
        /DataCloneError/
      );

      const recentChanges = await globalChanges;

      browser.test.assertEq(
        "value1",
        recentChanges["test-prop1"].oldValue,
        "oldValue correct"
      );
      browser.test.assertEq(
        "object",
        typeof recentChanges["test-prop1"].newValue,
        "newValue is obj"
      );
      clearGlobalChanges();

      data = await storage.get({
        "test-prop1": undefined,
        "test-prop2": undefined,
      });
      let obj = data["test-prop1"];

      if (areaName === "local") {
        browser.test.assertEq(
          String(date),
          String(obj.date),
          "date part correct"
        );
        browser.test.assertEq(
          "/regexp/",
          obj.regexp.toString(),
          "regexp part correct"
        );
      } else {
        browser.test.assertEq(
          "1970-01-01T00:00:00.000Z",
          String(obj.date),
          "date part correct"
        );

        browser.test.assertEq(
          "object",
          typeof obj.regexp,
          "regexp part is an object"
        );
        browser.test.assertEq(
          0,
          Object.keys(obj.regexp).length,
          "regexp part is an empty object"
        );
      }

      browser.test.assertEq("hello", obj.str, "string part correct");
      browser.test.assertEq(true, obj.bool, "bool part correct");
      browser.test.assertEq(null, obj.null, "null part correct");
      browser.test.assertEq(undefined, obj.undef, "undefined part correct");
      browser.test.assertEq(undefined, obj.window, "window part correct");
      browser.test.assertEq("object", typeof obj.obj, "object part correct");
      browser.test.assertTrue(Array.isArray(obj.arr), "array part present");
      browser.test.assertEq(1, obj.arr[0], "arr[0] part correct");
      browser.test.assertEq(2, obj.arr[1], "arr[1] part correct");
      browser.test.assertEq(2, obj.arr.length, "arr.length part correct");
    } catch (e) {
      browser.test.fail(`Error: ${e} :: ${e.stack}`);
      browser.test.notifyFail("storage");
    }
  }

  browser.test.onMessage.addListener(msg => {
    let promise;
    if (msg === "test-local") {
      promise = runTests("local");
    } else if (msg === "test-sync") {
      promise = runTests("sync");
    } else if (msg === "test-session") {
      promise = runTests("session");
    }
    promise.then(() => browser.test.sendMessage("test-finished"));
  });

  browser.test.sendMessage("ready");
}'''

CHECK_STORAGE_AREA_GET_BYTES_IN_USE = r'''async function check_storage_area_getBytesInUse(area) {
  let impl = browser.storage[area];

  browser.test.assertEq(
    typeof impl.getBytesInUse,
    "function",
    "getBytesInUse API method should be available"
  );
  browser.test.sendMessage("test-complete");
}'''

GET_BYTES_IN_USE_CONTENT_SCRIPT = r'''function contentScript(checkImpl) {
  browser.test.onMessage.addListener(msg => {
    if (msg === "test-local") {
      checkImpl("local");
    } else if (msg === "test-sync") {
      checkImpl("sync");
    } else if (msg === "test-session") {
      checkImpl("session");
    } else {
      browser.test.fail(`Unexpected test message received: ${msg}`);
      browser.test.sendMessage("test-complete");
    }
  });
  browser.test.sendMessage("ready");
}'''


def test_storage_after_reload(test, area_name, expect_persistency):
    # Just some random extension ID that we can re-use
    extension_id = 'my-extension-id@1'

    def load_extension():
        return test.load_extension(
            manifest={
                'browser_specific_settings': {'gecko': {'id': extension_id}},
                'permissions': ['storage'],
            },
            background=JS(AFTER_RELOAD_BACKGROUND, json.dumps(area_name)))

    extension1 = load_extension()
    extension1.startup()
    test.assertEqual(extension1.await_message('initialItems'), {}, 'No stored items at first')
    extension1.await_finish('set-works')
    extension1.unload()

    extension2 = load_extension()
    extension2.startup()
    test.assertEqual(extension2.await_message('initialItems'),
                     {'a': 'b'} if expect_persistency else {},
                     f"Expect {area_name} stored items {'to' if expect_persistency else 'not'} "
                     'be available after restart')
    extension2.await_finish('set-works')
    extension2.unload()


def test_background_page_storage(test, test_area_name):
    extension = test.load_extension(
        manifest={'permissions': ['storage']},
        background=JS(PAGE_STORAGE_BACKGROUND, CHECK_GET_IMPL))
    extension.startup()
    extension.await_message('ready')
    extension.send_message(f'test-{test_area_name}')
    extension.await_message('test-finished')
    extension.unload()


def test_storage_empty_events(test, area_name):
    extension = test.load_extension(
        manifest={'permissions': ['storage']},
        background=JS(EMPTY_EVENTS_BACKGROUND, json.dumps(area_name)))
    extension.startup()
    extension.await_message('ready')

    def call_storage_method(method, *arg):
        extension.send_message(method, *arg)
        extension.await_message('result')

    def expect_event(expect_count, expect_changes):
        test.assertEqual([expect_count, expect_changes], extension.await_message('onChanged'),
                         'Correct onChanged events count and data in the last changes notified.')

    call_storage_method('set', {'alpha': 1})
    expect_event(1, {'alpha': {'newValue': 1}})

    call_storage_method('set', {})
    # Setting nothing doesn't trigger onChanged event.

    call_storage_method('set', {'beta': 12})
    expect_event(2, {'beta': {'newValue': 12}})

    call_storage_method('remove', 'alpha')
    expect_event(3, {'alpha': {'oldValue': 1}})

    call_storage_method('remove', 'alpha')
    # Trying to remove alpha again doesn't trigger onChanged.

    call_storage_method('clear')
    expect_event(4, {'beta': {'oldValue': 12}})

    call_storage_method('clear')
    # Clear again wothout onChanged. Test will fail on unexpected event/message.

    extension.unload()


def test_storage_change_event_page(test, area_name):
    def test_on_changed(target_is_storage_area):
        # Test storage.local.onChanged / storage.sync.onChanged, or
        # storage.onChanged.
        background = (ON_CHANGED_AREA_NAMESPACE if target_is_storage_area
                      else ON_CHANGED_TOP_NAMESPACE)
        extension = test.load_extension(
            manifest={
                'permissions': ['storage'],
                'background': {'persistent': False},
            },
            background=JS(background, json.dumps(area_name)),
            files={
                'trigger-change.html': """
          <!DOCTYPE html><meta charset="utf-8">
          <script src="trigger-change.js"></script>
        """,
                'trigger-change.js': JS(TRIGGER_CHANGE),
            })
        extension.startup()
        extension.terminate_background()

        # Now trigger the event
        page = test.open_tab(f'chrome-extension://{extension.id}/trigger-change.html?{area_name}')
        extension.await_message('tried_to_trigger_change')
        test.browser.close_target(page)
        extension.await_message('onChanged_was_fired')
        extension.unload()

    # Test browser.storage.onChanged.addListener
    test_on_changed(False)
    # Test browser.storage.local.onChanged.addListener
    # and browser.storage.sync.onChanged.addListener, depending on areaName.
    test_on_changed(True)


def test_get_bytes_in_use(test, area_name, is_idb_backend='undefined'):
    """`is_idb_backend` is JavaScript source, as Firefox puts the argument in
    the background's source."""
    extension = test.load_extension(
        manifest={
            'permissions': ['storage'],
            'browser_specific_settings': {'gecko': {'id': 'test-getBytesInUse@mozilla.org'}},
        },
        background=JS(CHECK_GET_BYTES_IN_USE, json.dumps(area_name), is_idb_backend))
    extension.startup()
    extension.await_message('test-finished')
    extension.unload()


def test_contentscript_storage_area_getBytesInUse(test, area):
    """The test class serves Firefox's data/file_sample.html at
    http://example.com/data/file_sample.html."""
    content_page = test.open_tab('http://example.com/data/file_sample.html')

    extension = test.load_extension(
        manifest={
            'content_scripts': [{
                'matches': ['http://example.com/data/file_sample.html'],
                'js': ['content_script.js'],
                'run_at': 'document_idle',
            }],
            'permissions': ['storage'],
        },
        files={
            'content_script.js': JS(GET_BYTES_IN_USE_CONTENT_SCRIPT,
                                    CHECK_STORAGE_AREA_GET_BYTES_IN_USE),
        })
    extension.startup()
    extension.await_message('ready')

    extension.send_message(f'test-{area}')
    extension.await_message('test-complete')

    extension.unload()
    test.browser.close_target(content_page)


def test_contentscript_storage(test, storage_type):
    """As test_contentscript_storage_area_getBytesInUse(), the test class
    serves the content page."""
    content_page = test.open_tab('http://example.com/data/file_sample.html')

    extension = test.load_extension(
        manifest={
            'content_scripts': [{
                'matches': ['http://example.com/data/file_sample.html'],
                'js': ['content_script.js'],
                'run_at': 'document_idle',
            }],
            'permissions': ['storage'],
        },
        files={
            'content_script.js': JS(STORAGE_CONTENT_SCRIPT, CHECK_GET_IMPL),
        })
    extension.startup()
    extension.await_message('ready')

    extension.send_message(f'test-{storage_type}')
    extension.await_message('test-finished')

    extension.unload()
    test.browser.close_target(content_page)
