# Pythia Copilot (Chrome extension)

Story 2's entry point. On any page, highlight a ticker or a company name,
right-click, and choose **Analyse unusual activity**. The desk opens in Copilot
mode on that security.

## Install

1. `make dev` (the desk must be running).
2. Chrome → `chrome://extensions` → enable **Developer mode**.
3. **Load unpacked** → select this `extension/` folder.

If the desk is not on `http://localhost:5173`, set its URL in the extension's
options.

## What it sends

Only the text you highlighted, as `?mode=copilot&ticker=<selection>` to your own
desk. Nothing goes anywhere else, and the extension reads no page content.
