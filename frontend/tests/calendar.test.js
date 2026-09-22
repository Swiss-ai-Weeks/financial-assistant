import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addDays,
  isWeekend,
  lastWeekday,
  monthGrid,
  replayBounds,
  shiftMonth,
} from "../src/lib/calendar.js";

test("the replay bounds are the last year of weekdays up to the latest session", () => {
  // 2026-09-20 is a Sunday: the latest session is the Friday before.
  assert.deepEqual(replayBounds("2026-09-20"), { min: "2025-09-18", max: "2026-09-18" });
  assert.deepEqual(replayBounds("2026-09-22"), { min: "2025-09-22", max: "2026-09-22" });
});

test("weekends are closed", () => {
  assert.equal(isWeekend("2026-09-19"), true);
  assert.equal(isWeekend("2026-09-21"), false);
  assert.equal(lastWeekday("2026-09-20"), "2026-09-18");
});

test("a month grid is six Monday-first rows around the month", () => {
  const grid = monthGrid({ year: 2026, month: 2 }); // March 2026 starts on a Sunday

  assert.equal(grid.length, 42);
  assert.equal(grid[0], "2026-02-23");
  assert.equal(grid[6], "2026-03-01");
  assert.equal(grid[41], "2026-04-05");
});

test("month navigation wraps years and day arithmetic crosses months", () => {
  assert.deepEqual(shiftMonth({ year: 2026, month: 0 }, -1), { year: 2025, month: 11 });
  assert.deepEqual(shiftMonth({ year: 2025, month: 11 }, 1), { year: 2026, month: 0 });
  assert.equal(addDays("2026-02-28", 1), "2026-03-01");
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
});
