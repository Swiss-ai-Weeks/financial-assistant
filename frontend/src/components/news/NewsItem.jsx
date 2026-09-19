import { dateTime } from "../../lib/format";
import { ExternalIcon } from "../icons";

export default function NewsItem({ item, dimmed = false }) {
  return (
    <a
      className={`news-item ${dimmed ? "is-dimmed" : ""}`}
      href={item.url}
      target="_blank"
      rel="noreferrer"
    >
      <div className="news-item__meta mono">
        <span className="news-item__ticker">{item.ticker}</span>
        <span>{dateTime(item.published_at)} UTC</span>
        <span className="news-item__publisher">{item.publisher}</span>
        <ExternalIcon size={13} />
      </div>
      <div className="news-item__title">{item.title}</div>
      {item.summary && <p className="news-item__summary">{item.summary}</p>}
    </a>
  );
}
