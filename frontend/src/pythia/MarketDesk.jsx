import {useEffect, useState} from 'react';
import Tabs from './Tabs.jsx';
import {deskRequest, holdingCandidate} from './deskClient.js';
import NewsFeed from './NewsFeed.jsx';
import {sessionNews} from './newsModel.js';
import DetectorPanel from '../DetectorPanel.jsx';
const percent = value => typeof value === 'number' ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}%` : '—';
const ranges = [['1d','1D'],['1w','1W'],['1m','1M'],['3m','3M'],['1y','1Y']];

export function SecuritySearch({onSelect}) {
  const [query,setQuery] = useState(''), [result,setResult] = useState(null), [error,setError] = useState('');
  useEffect(() => {
    if (!query.trim()) return;
    const controller = new AbortController();
    const timer = setTimeout(() => deskRequest('/api/instruments/search',{q:query},controller.signal).then(r => {setResult({query,...r});setError('');}).catch(e => {if (e.name !== 'AbortError') setError(e.message);}),180);
    return () => {clearTimeout(timer);controller.abort();};
  },[query]);
  return <div className="security-search"><label>Find a security<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Ticker or company name" /></label>{error && <p role="status">{error}</p>}
    {query.trim() && result?.query === query && <div className="search-results">{result.securities.map(s => <button key={s.identity} onClick={() => {onSelect(s.ticker);setQuery('');}}><strong>{s.ticker}</strong> {s.name}<small>{s.catalogued ? 'Catalogued' : 'Yahoo resolved'} · {s.universes.length ? s.universes.join(' · ') + ' (current membership)' : 'No configured universe membership'} · {s.coverage?.precomputed_pairs ? 'Precomputed pairs available' : 'No known precomputed pairs'}</small></button>)}{!result.securities.length && <p>No security resolved. Try another ticker or company name.</p>}{result.yahoo_status === 'unavailable' && <p role="status">Yahoo search unavailable; showing catalog matches.</p>}<small>{result.limitation}</small></div>}
  </div>;
}

export default function MarketDesk({mode, ticker, onTicker, asOf, onAsOf, portfolio, onInvestigate, active=true, discoveryCandidate=null}) {
  const [data,setData] = useState(null), [error,setError] = useState(''), [loading,setLoading] = useState(false);
  const [horizon,setHorizon] = useState('1w'), [tab,setTab] = useState('anomalies'), [day,setDay] = useState(null);
  const [selected,setSelected] = useState(null), [refresh,setRefresh] = useState(0);
  const [days,setDays] = useState(180);
  const bookKey = JSON.stringify(portfolio);
  const requestKey = `${mode}:${ticker}:${asOf}:${days}:${refresh}:${bookKey}`;
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    async function load() {
      setLoading(true); setError('');
      try {
        let date=asOf;
        if (mode === 'now') {
          const response=await fetch('/api/health',{signal:controller.signal});
          if (!response.ok) throw new Error('Market API unavailable');
          const health=await response.json(); date=health.market_as_of ?? health.as_of;
          if (!date) throw new Error('Market cache unavailable. Saved investigations remain available in Investigate.');
        }
        const results=await Promise.allSettled([
          deskRequest(`/api/market/${encodeURIComponent(ticker)}/candles`,{as_of:date,days},controller.signal),
          deskRequest(`/api/microscope/${encodeURIComponent(ticker)}`,{as_of:date},controller.signal),
          deskRequest('/api/news',{ticker,as_of:date,days,limit:200},controller.signal),
          deskRequest(`/api/market/${encodeURIComponent(ticker)}/signals`,{as_of:date},controller.signal),
          fetch('/api/portfolio/analysis',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({portfolio:JSON.parse(bookKey),as_of:date})}).then(r => {if(!r.ok) throw new Error('Portfolio context unavailable');return r.json();}),
        ]);
        if (controller.signal.aborted) return;
        setData({key:requestKey,date,market:results[0].value,scope:results[1].value,news:results[2].value,signals:results[3].value,book:results[4].value,
          errors:results.filter(r => r.status === 'rejected').map(r => r.reason.message)});
      } catch(e) {if (!controller.signal.aborted) setError(e.message);}
      finally {if (!controller.signal.aborted) setLoading(false);}
    }
    load(); return () => controller.abort();
  },[mode,ticker,asOf,days,refresh,requestKey,active,bookKey]);
  const current = data?.key === requestKey ? data : null;
  const reading=current?.scope?.ticks.find(t => t.horizon === horizon);
  const activeDate=current?.date ?? (mode === 'past' ? asOf : null);
  const news=sessionNews(current?.news?.admissible ?? current?.news?.items,day);
  const choose = symbol => {onTicker(symbol);setDay(null);setSelected(null);};
  return <div className="market-desk">
    <header className="desk-heading"><div><span className="eyebrow">{mode === 'now' ? 'NOW / SECURITY MICROSCOPE' : 'PAST / HISTORICAL REVIEW'}</span><h1>{ticker} <small>{mode === 'now' ? 'What is unusual?' : 'What was knowable?'}</small></h1></div><SecuritySearch onSelect={choose}/></header>
    <div className="desk-strip"><div><span className="eyebrow">{mode === 'now' ? 'Latest cached session' : 'Selected cutoff'}</span><strong>{activeDate ?? 'Unavailable'}</strong></div>{ranges.map(([key,label]) => <button key={key} className={horizon === key ? 'is-active' : ''} onClick={() => setHorizon(key)}>{label}<small>{percent(current?.scope?.ticks.find(t => t.horizon === key)?.abnormal_return_pct)}</small></button>)}<button onClick={() => setRefresh(n => n+1)}>Refresh</button></div>
    {mode === 'past' && <label className="desk-date">Review as of <input type="date" value={asOf} onChange={e => {onAsOf(e.target.value);setDay(null);setSelected(null);}} /></label>}
    {loading && <p role="status">Reading market context…</p>}{error && <p className="desk-error" role="alert">{error}</p>}{current?.errors.map(e => <p className="desk-error" key={e}>{e}</p>)}
    <div className="desk-columns"><main><div className="desk-toolbar"><span className="eyebrow">PRICE HISTORY · SELECT A SESSION FOR NEWS</span><div>{[[30,'1M'],[90,'3M'],[180,'6M'],[365,'1Y']].map(([n,label]) => <button key={n} aria-pressed={days===n} onClick={() => setDays(n)}>{label}</button>)}</div></div>
      <PriceHistory candles={current?.market?.candles ?? []} day={day} onDay={value => {setDay(value);setTab('news');}}/>
      <Tabs tabs={[{key:'anomalies',label:'Pairs'},{key:'signals',label:'Monitors'},{key:'peers',label:'Peers'},{key:'positions',label:'Positions'},{key:'news',label:'News',count:news.length}]} active={tab} onChange={setTab}/>
      <div hidden={tab !== 'anomalies'} className="desk-blotter"><DetectorPanel initialMode={mode === 'past' ? 'historical' : 'live'} lockMode sharedAsOf={asOf} onAsOf={onAsOf} onSelectCandidate={candidate => {setSelected(candidate); if(candidate) onTicker(candidate.ticker_a);}}/></div>
      {tab === 'signals' && <div className="desk-news"><p>VWAP / TWAP / trend · attention events, not causal findings</p>{current?.signals?.signals.map(signal => <article key={signal.anomaly_id}><span className="eyebrow">{signal.strategy} · {signal.observed_on}</span><h3>{signal.summary}</h3><p>Deviation {signal.z_score.toFixed(2)}σ</p><button onClick={() => onInvestigate({...holdingCandidate(ticker,signal.observed_on),event_context:signal})}>Investigate this event →</button></article>)}{!current?.signals?.signals.length && <p>{current?.signals?.reason ?? 'No monitor fired in the selected review window.'}</p>}</div>}
      {tab === 'peers' && <div className="desk-news"><p>Peers measured before the {horizon} horizon · descriptive co-movement</p>{current?.scope?.peers?.[horizon]?.map(peer => <article key={peer.ticker}><button onClick={() => choose(peer.ticker)}>{peer.ticker}</button><p>Correlation {peer.correlation.toFixed(2)} · abnormal {percent(peer.abnormal_return_pct)} · {peer.followed ? 'followed' : 'did not follow'}</p></article>)}{!current?.scope?.peers?.[horizon]?.length && <p>No eligible peer history at this cutoff.</p>}</div>}
      {tab === 'positions' && <div className="desk-positions">{portfolio.positions.map(p => <button key={p.ticker} onClick={() => choose(p.ticker)}>{p.ticker}<span>{(p.weight*100).toFixed(1)}% weight · 20-session contribution {percent(current?.book?.contributions_20?.[p.ticker] == null ? null : current.book.contributions_20[p.ticker]*100)}</span></button>)}</div>}
      {tab === 'news' && <NewsFeed ticker={ticker} feed={current?.news} day={day} onClearDay={() => setDay(null)}/>}
    </main><aside className="desk-context"><span className="eyebrow">{ticker} / {horizon.toUpperCase()}</span><h2>{reading?.status === 'available' ? reading.unusual ? 'Unusual at this horizon' : 'Within historical range' : 'Market context'}</h2>
      {reading?.status === 'available' ? <><div className="scope-metrics"><div>Return<strong>{percent(reading.return_pct)}</strong></div><div>Market<strong>{percent(reading.benchmark_return_pct)}</strong></div><div>Abnormal<strong>{percent(reading.abnormal_return_pct)}</strong></div><div>Deviation<strong>{reading.z_score.toFixed(2)}σ</strong></div></div><p>Volume {reading.volume_multiple.toFixed(2)}× its earlier baseline.</p></> : <p>{reading?.reason ?? 'Load market history to inspect measured context.'}</p>}
      <p>{current?.scope?.methodology}</p>{mode === 'past' && <section><h3>Portfolio impact</h3><p>20-session contribution: {percent(current?.book?.contributions_20?.[ticker] == null ? null : current.book.contributions_20[ticker]*100)}</p><p>{current?.book?.status === 'unavailable' ? current.book.reason : 'Calculated from the same saved portfolio weights and cutoff as Portfolio.'}</p></section>}<h3>What explains the move?</h3><p>Market measurements direct attention. ClaimGraph tests explanations against sources, calculations and counter-evidence.</p>
      <button className="primary-action" disabled={!activeDate} onClick={() => onInvestigate(holdingCandidate(ticker,activeDate))}>Investigate {ticker} →</button>
      {discoveryCandidate && discoveryCandidate.requested_as_of === activeDate && [discoveryCandidate.ticker_a,discoveryCandidate.ticker_b].includes(ticker) && <section><h3>Discovery · {discoveryCandidate.pair}</h3><p>Inspect both securities and their news before investigating the relationship.</p><button onClick={() => choose(ticker === discoveryCandidate.ticker_a ? discoveryCandidate.ticker_b : discoveryCandidate.ticker_a)}>Inspect other security →</button><button className="primary-action" onClick={() => onInvestigate(discoveryCandidate)}>Investigate discovery →</button></section>}
      {selected && <section><h3>{selected.pair}</h3><p>Detected {selected.signal_date} · z {selected.z_score?.toFixed(2)}</p><button className="primary-action" onClick={() => onInvestigate(selected)}>Investigate anomaly →</button></section>}
      <details><summary>Market / membership provenance</summary><p>{current?.market?.source}</p><p>{current?.market?.universe_limitation ?? 'Current constituent snapshots only; not historical membership.'}</p><pre>{JSON.stringify(current?.market?.metrics,null,2)}</pre></details>
    </aside></div>
  </div>;
}
function PriceHistory({candles,day,onDay}) {
  if (!candles.length) return <div className="price-empty">Price history unavailable for this security and cutoff.</div>;
  const values=candles.map(c => c.close), low=Math.min(...values), high=Math.max(...values), span=high-low || 1;
  const x=i => 40+i/Math.max(candles.length-1,1)*820, y=value => 240-(value-low)/span*200;
  return <div className="price-history"><svg viewBox="0 0 900 290" role="img" aria-label="Closing price history"><path d={candles.map((c,i) => `${i ? 'L':'M'}${x(i)},${y(c.close)}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth="2"/>{[low,(low+high)/2,high].map((v,i) => <g key={i}><line x1="40" x2="860" y1={y(v)} y2={y(v)} stroke="var(--border)"/><text x="42" y={y(v)-7} fill="var(--text-muted)" fontSize="12">{v.toFixed(2)}</text></g>)}{candles.map((c,i) => <rect key={c.date} x={x(i)-4} y="25" width={Math.max(8,820/candles.length)} height="230" fill={day === c.date ? 'var(--accent-soft)' : 'transparent'} opacity=".5" onClick={() => onDay(c.date)}><title>{c.date}: {c.close.toFixed(2)}</title></rect>)}<text x="40" y="280" fill="var(--text-muted)" fontSize="12">{candles[0].date}</text><text x="790" y="280" fill="var(--text-muted)" fontSize="12">{candles.at(-1).date}</text></svg><label>Session <select value={day ?? ''} onChange={e => onDay(e.target.value)}><option value="">Select a session</option>{candles.map(c => <option key={c.date}>{c.date}</option>)}</select></label></div>;
}
