import {useEffect, useRef, useState} from 'react';
import {CloverIcon} from './icons.jsx';
import {discover} from './discovery.js';
import './discovery.css';

export default function DiscoveryView({asOf, portfolio, onInspect}) {
  const [state,setState] = useState({status:'idle'});
  const controller = useRef(null);
  const key = JSON.stringify([asOf,portfolio.positions]);
  useEffect(() => () => controller.current?.abort(), [key]);
  async function scan() {
    controller.current?.abort();
    const current = new AbortController(); controller.current = current;
    setState({status:'running',key});
    try {
      const result = await discover({asOf,positions:portfolio.positions,signal:current.signal});
      if (!current.signal.aborted) setState({status:'completed',key,...result});
    } catch(error) {
      if (!current.signal.aborted) setState({status:'failed',key,error:error.message});
    }
  }
  const current = state.key === key ? state : {status:'idle'};
  const candidate = current.candidate;
  return <div className="discovery">
    <header className="discovery__hero">
      <span className="eyebrow">Market → anomalies → one idea</span>
      <h1>What should I be looking at?</h1>
      <button className="discovery__button" disabled={current.status === 'running'} onClick={scan}>
        <CloverIcon size={20}/>{current.status === 'running' ? 'Scanning the universe…' : 'I’m Feeling Lucky'}
      </button>
      {current.status === 'running' && <p role="status">Testing relationships at {asOf}…</p>}
      {current.status === 'failed' && <p role="alert">{current.error}</p>}
    </header>
    {current.status === 'completed' && <article className="setup is-leading" aria-label="Discovery result">
      {candidate ? <>
        <span className="eyebrow">{current.alreadyHeld ? 'Already on your desk' : '🍀 Today’s discovery'}</span>
        <h2>{candidate.pair}</h2>
        <div className="setup__figures"><div><span className="eyebrow">Anomaly</span>{Math.abs(candidate.z_score).toFixed(1)}σ</div><div><span className="eyebrow">Correlation</span>{candidate.correlation.toFixed(2)}</div><div><span className="eyebrow">Cointegration p</span>{candidate.cointegration_p.toFixed(4)}</div></div>
        <section><span className="eyebrow">Why now</span><p>An unusual relationship at {current.scan.resolved_session ?? current.scan.as_of}. {current.alreadyHeld && 'Involves a holding; no new resolvable pair outside your book cleared the bar.'}</p></section>
        <section><span className="eyebrow">Why these securities are connected</span><p>Historically correlated returns and a cointegrated price relationship. Inspect market and news context to examine the economic connection.</p></section>
        <section><span className="eyebrow">What would invalidate it</span><p>A lasting company-specific event or a broken relationship can explain the gap. Deviation alone does not establish a cause or predict convergence.</p></section>
        <p>Research cutoff: {asOf} · Formation: {candidate.formation_start ?? 'Unavailable'} — {candidate.formation_end ?? 'Unavailable'}</p>
        {current.securities.map(s => <button key={s.identity} onClick={() => onInspect(candidate,s.ticker)}>Inspect {s.ticker} · {s.name} →</button>)}
      </> : <><h2>Nothing new clears the bar today</h2><p>No valid, resolvable relationship passed the discovery filters at this cutoff.</p></>}
      <p className="discovery__basis">Ranked by absolute deviation among returned scan candidates; pairs outside your holdings come first. Correlation ≥ 0.65, cointegration p ≤ 0.05, deviation ≥ 1.5σ. Coverage is the merged analytical cache, not every Yahoo-searchable security. Liquidity, historical analogue returns and model triage are not evaluated here.</p>
      <p className="discovery__disclaimer">A research signal. Not investment advice. Inspect the context, then choose Investigate to open ClaimGraph.</p>
    </article>}
  </div>;
}
