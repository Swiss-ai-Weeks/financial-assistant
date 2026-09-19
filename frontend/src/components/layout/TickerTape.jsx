import { price, tone } from "../../lib/format";

/** The book's holdings, scrolling along the bottom edge. */
export default function TickerTape({ quotes, llm, onSelect }) {
  return (
    <footer className="tape">
      <div className="tape__track mono">
        {quotes.map((quote) => (
          <button
            key={quote.ticker}
            className="tape__item"
            onClick={() => onSelect(quote.ticker)}
          >
            <span>{quote.ticker}</span>
            <span className={tone(quote.change_pct)}>{price(quote.last)}</span>
          </button>
        ))}
      </div>

      <div className="tape__status" title={llm?.detail}>
        <span className={`dot ${llm?.online ? "dot--on" : "dot--off"}`} />
      </div>
    </footer>
  );
}
