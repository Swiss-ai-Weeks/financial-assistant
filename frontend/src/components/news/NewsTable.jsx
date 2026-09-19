import { dateTime } from "../../lib/format";

/** Book-wide wire, for the bottom blotter. */
export default function NewsTable({ news, loading, onSelectTicker }) {
  if (loading && !news) {
    return <div className="empty">Loading the wire…</div>;
  }

  if (!news?.length) {
    return <div className="empty">No news for the holdings.</div>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Published (UTC)</th>
          <th>Market</th>
          <th>Source</th>
          <th>Headline</th>
        </tr>
      </thead>
      <tbody>
        {news.map((item) => (
          <tr key={item.news_id} onClick={() => onSelectTicker(item.ticker)}>
            <td className="mono">{dateTime(item.published_at)}</td>
            <td className="mono strong">{item.ticker}</td>
            <td className="muted">{item.publisher}</td>
            <td className="table__wide">
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
              >
                {item.title}
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
