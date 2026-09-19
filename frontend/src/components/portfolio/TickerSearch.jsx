import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import { ChevronIcon, PlusIcon, SearchIcon } from "../icons";

const DEBOUNCE_MS = 250;

/**
 * Symbol picker of the top bar.
 *
 * Selecting a result opens it on the desk. "Add" also
 * puts it in the book, which triggers the pair scan.
 */
export default function TickerSearch({ ticker, holdings, onSelect, onAdd }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const root = useRef(null);

  const timer = useRef(null);

  const search = (value) => {
    setText(value);
    clearTimeout(timer.current);

    if (!value.trim()) {
      setResults([]);
      setSearching(false);
      return;
    }

    setSearching(true);

    timer.current = setTimeout(() => {
      api
        .searchInstruments(value.trim())
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, DEBOUNCE_MS);
  };

  useEffect(() => () => clearTimeout(timer.current), []);

  useEffect(() => {
    const close = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };

    document.addEventListener("mousedown", close);

    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (symbol, add) => {
    setOpen(false);
    search("");

    if (add) onAdd(symbol);
    else onSelect(symbol);
  };

  return (
    <div className="search" ref={root}>
      <button className="search__current" onClick={() => setOpen(!open)}>
        <span className="search__badge mono">{ticker?.slice(0, 1)}</span>
        <span className="search__ticker">{ticker}</span>
        <ChevronIcon size={20} />
      </button>

      {open && (
        <div className="search__panel">
          <label className="search__input">
            <SearchIcon size={18} />
            <input
              autoFocus
              value={text}
              placeholder="Search a company or ticker…"
              onChange={(event) => search(event.target.value)}
            />
            {searching && <span className="spinner" />}
          </label>

          {!text.trim() && (
            <>
              <div className="search__heading eyebrow">In the book</div>
              {holdings.map((position) => (
                <button
                  key={position.ticker}
                  className="search__row"
                  onClick={() => choose(position.ticker, false)}
                >
                  <span className="mono search__symbol">{position.ticker}</span>
                  <span className="search__name">{position.name}</span>
                </button>
              ))}
            </>
          )}

          {results.map((instrument) => {
            const held = holdings.some((p) => p.ticker === instrument.ticker);

            return (
              <div key={instrument.ticker} className="search__row">
                <button
                  className="search__pick"
                  onClick={() => choose(instrument.ticker, false)}
                >
                  <span className="mono search__symbol">{instrument.ticker}</span>
                  <span className="search__name">
                    {instrument.name}
                    <small>
                      {[instrument.exchange, instrument.sector]
                        .filter(Boolean)
                        .join(" · ")}
                    </small>
                  </span>
                </button>

                <button
                  className="btn btn--small"
                  disabled={held}
                  onClick={() => choose(instrument.ticker, true)}
                >
                  {held ? "Held" : <><PlusIcon size={14} /> Add</>}
                </button>
              </div>
            );
          })}

          {text.trim() && !searching && results.length === 0 && (
            <div className="empty">No tradable instrument matches “{text}”.</div>
          )}
        </div>
      )}
    </div>
  );
}
