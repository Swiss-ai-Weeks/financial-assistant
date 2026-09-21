/*
 * What the desk already fetched, kept across view changes and
 * page reloads.
 *
 * Leaving a view used to throw its data away, so coming back
 * to the news or to a ClaimGraph meant waiting for it again.
 * Here every response is remembered under its resource key:
 *
 *   - a remembered answer is shown at once, and refreshed
 *     behind the scenes only when it is older than `maxAge`;
 *   - keys marked `persist` also survive a reload of the page
 *     (localStorage), which is what makes reopening a graph
 *     or a feed instant.
 *
 * Pure and storage-agnostic, so it runs under node --test.
 */

const PREFIX = "pythia:cache:";

// One entry may not take the whole quota: a ClaimGraph with its
// SEC observations runs to a few hundred kilobytes.
const MAX_PERSISTED_CHARS = 1_500_000;

export function createResourceCache(storage = null, now = () => Date.now()) {
  const memory = new Map();

  function read(key) {
    if (memory.has(key)) return memory.get(key);

    if (!storage) return null;

    try {
      const raw = storage.getItem(PREFIX + key);

      if (!raw) return null;

      const entry = JSON.parse(raw);

      memory.set(key, entry);

      return entry;
    } catch {
      return null;
    }
  }

  function write(key, data, { persist = false } = {}) {
    const entry = { data, at: now() };

    memory.set(key, entry);

    if (!persist || !storage) return entry;

    try {
      const raw = JSON.stringify(entry);

      if (raw.length <= MAX_PERSISTED_CHARS) storage.setItem(PREFIX + key, raw);
    } catch {
      // Quota exceeded or storage disabled: memory still holds
      // it for this visit, which is all that was promised.
      evictOldest();
    }

    return entry;
  }

  function evictOldest() {
    if (!storage) return;

    try {
      const entries = [];

      for (let index = 0; index < storage.length; index += 1) {
        const name = storage.key(index);

        if (name?.startsWith(PREFIX)) {
          entries.push([name, JSON.parse(storage.getItem(name))?.at ?? 0]);
        }
      }

      entries
        .sort((a, b) => a[1] - b[1])
        .slice(0, Math.ceil(entries.length / 2))
        .forEach(([name]) => storage.removeItem(name));
    } catch {
      // Nothing to free.
    }
  }

  function isFresh(key, maxAge) {
    const entry = read(key);

    return entry != null && now() - entry.at < maxAge;
  }

  function forget(match) {
    const matches = (key) =>
      typeof match === "function" ? match(key) : key.startsWith(match);

    [...memory.keys()].filter(matches).forEach((key) => memory.delete(key));

    if (!storage) return;

    try {
      const names = [];

      for (let index = 0; index < storage.length; index += 1) {
        const name = storage.key(index);

        if (name?.startsWith(PREFIX) && matches(name.slice(PREFIX.length))) {
          names.push(name);
        }
      }

      names.forEach((name) => storage.removeItem(name));
    } catch {
      // Best effort.
    }
  }

  return { read, write, isFresh, forget };
}

function browserStorage() {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export const resourceCache = createResourceCache(browserStorage());
