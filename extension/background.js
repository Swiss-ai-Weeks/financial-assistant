// Story 2 entry point: the trader is reading Bloomberg, Yahoo
// Finance or broker research, highlights a ticker, and asks
// the desk what is unusual about it.
//
// The extension does no analysis itself. It hands the selection
// to the desk, which resolves company names to tickers.

const DEFAULT_DESK = "http://localhost:5173";
const MENU_ID = "claimgraph-analyse";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: 'Analyse unusual activity: "%s"',
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return;

  const { desk = DEFAULT_DESK } = await chrome.storage.sync.get("desk");

  // "$NVDA", "NVDA:US" and "(NYSE: BAC)" all reduce to the symbol.
  const selection = info.selectionText
    .trim()
    .replace(/^\$/, "")
    .replace(/^\(?\s*(NYSE|NASDAQ|NYSEARCA)\s*:\s*/i, "")
    .replace(/[):].*$/, "")
    .trim();

  const url = new URL(desk);
  url.searchParams.set("mode", "copilot");
  url.searchParams.set("ticker", selection);

  chrome.tabs.create({ url: url.toString() });
});
