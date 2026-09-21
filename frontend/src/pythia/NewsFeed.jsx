import {sessionNews} from './newsModel.js';

function Story({item}) {
  return <article><span className="eyebrow">{item.publisher ?? 'Unknown publisher'} · <time dateTime={item.published_at}>{item.published_at.replace('T',' ').replace('+00:00',' UTC')}</time>{item.published_date_only && ' · date only (conservative availability)'}</span>
    <h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h3>
    {item.summary && <p>{item.summary}</p>}
    <small>Source: {[...new Set((item.provenance ?? [{source:item.source}]).map(p => p.source))].join(' + ')} · {item.cutoff_availability === 'hindsight' ? 'Hindsight — excluded from contemporaneous input' : 'Admissible by publication time — unassessed'}</small>
  </article>;
}

export default function NewsFeed({ticker, feed, day, onClearDay}) {
  const admissible = sessionNews(feed?.admissible ?? feed?.items, day);
  const hindsight = sessionNews(feed?.hindsight, day);
  return <div className="desk-news"><h2>{ticker} news</h2><p>Discovery context · relevance is not evidential support. {day && <button onClick={onClearDay}>Clear session {day} ×</button>}</p>
    {Object.entries(feed?.availability ?? {}).map(([symbol,status]) => <div key={symbol} role="status">{status['yahoo-finance'] === 'unavailable' && <p>Yahoo news unavailable for {symbol}; showing archive and previously cached stories.</p>}{status.pythia_archive === 'unavailable' && <p>Local archive unavailable for {symbol}.</p>}</div>)}
    <h3>Admissible news · {admissible.length}</h3>{feed?.cutoff && <p>Published by {feed.cutoff} · requires ClaimGraph evidence assessment</p>}
    {admissible.map(item => <Story key={item.news_id} item={item}/>)}
    {!admissible.length && <p>No admissible stories for this selection. Investigate to search BookReader, web and SEC sources.</p>}
    {hindsight.length > 0 && <section aria-label="Hindsight news"><h3>Hindsight · {hindsight.length}</h3><p>Published after the cutoff; never contemporaneous evidence.</p>{hindsight.map(item => <Story key={item.news_id} item={item}/>)}</section>}
  </div>;
}
