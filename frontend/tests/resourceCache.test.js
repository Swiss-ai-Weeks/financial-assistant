import test from "node:test";
import assert from "node:assert/strict";

import { createResourceCache } from "../src/lib/resourceCache.js";

function fakeStorage() {
  const items = new Map();

  return {
    get length() {
      return items.size;
    },
    key: (index) => [...items.keys()][index] ?? null,
    getItem: (name) => items.get(name) ?? null,
    setItem: (name, value) => items.set(name, value),
    removeItem: (name) => items.delete(name),
    items,
  };
}

test("an answer is remembered and fresh until it ages out", () => {
  let now = 1_000;
  const cache = createResourceCache(null, () => now);

  assert.equal(cache.read("news:BAC"), null);

  cache.write("news:BAC", [{ title: "x" }]);

  assert.deepEqual(cache.read("news:BAC").data, [{ title: "x" }]);
  assert.ok(cache.isFresh("news:BAC", 60_000));

  now += 61_000;

  // Stale, but still shown while it is refreshed.
  assert.equal(cache.isFresh("news:BAC", 60_000), false);
  assert.deepEqual(cache.read("news:BAC").data, [{ title: "x" }]);
});

test("only persisted keys survive a reload of the page", () => {
  const storage = fakeStorage();
  const before = createResourceCache(storage, () => 5);

  before.write("investigation:INV-1", { graph: { nodes: [] } }, { persist: true });
  before.write("quote:BAC", { last: 1 });

  const after = createResourceCache(storage, () => 6);

  assert.deepEqual(after.read("investigation:INV-1").data, { graph: { nodes: [] } });
  assert.equal(after.read("quote:BAC"), null);
});

test("a full or broken storage never breaks the desk", () => {
  const storage = fakeStorage();

  storage.setItem = () => {
    throw new Error("QuotaExceededError");
  };

  const cache = createResourceCache(storage, () => 1);

  cache.write("news:BAC", [1, 2, 3], { persist: true });

  assert.deepEqual(cache.read("news:BAC").data, [1, 2, 3]);

  storage.getItem = () => "{not json";

  assert.equal(createResourceCache(storage).read("anything"), null);
});

test("forgetting by prefix clears memory and storage", () => {
  const storage = fakeStorage();
  const cache = createResourceCache(storage, () => 1);

  cache.write("news:BAC:live", [1], { persist: true });
  cache.write("news:JPM:live", [2], { persist: true });

  cache.forget("news:BAC");

  assert.equal(cache.read("news:BAC:live"), null);
  assert.deepEqual(cache.read("news:JPM:live").data, [2]);
  assert.equal(createResourceCache(storage).read("news:BAC:live"), null);
});
