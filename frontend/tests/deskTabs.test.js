import test from "node:test";
import assert from "node:assert/strict";

import { BOTTOM_TABS, SIDE_TABS, resolveTab } from "../src/lib/deskTabs.js";

test("a tab the view has is kept", () => {
  assert.equal(resolveTab(BOTTOM_TABS, "copilot", "peers"), "peers");
  assert.equal(resolveTab(BOTTOM_TABS, "postmortem", "news"), "news");
  assert.equal(resolveTab(SIDE_TABS, "postmortem", "monitors"), "monitors");
});

test("a tab remembered from the other view falls back to the first", () => {
  // Now -> Why -> Past used to leave "peers" in Past: a panel
  // stuck on "Measuring…" because Past never loads the microscope.
  assert.equal(resolveTab(BOTTOM_TABS, "postmortem", "peers"), "anomalies");
  assert.equal(resolveTab(BOTTOM_TABS, "copilot", "positions"), "peers");
  assert.equal(resolveTab(SIDE_TABS, "copilot", "monitors"), "findings");
});

test("views without a desk resolve as Past", () => {
  assert.equal(resolveTab(BOTTOM_TABS, "graph", "peers"), "anomalies");
  assert.equal(resolveTab(BOTTOM_TABS, "graph", "news"), "news");
});
