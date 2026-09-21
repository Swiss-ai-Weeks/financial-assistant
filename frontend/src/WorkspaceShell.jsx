import {createContext, useCallback, useEffect, useReducer, useState} from 'react';
import Investigation from './App';
import DetectorPanel from './DetectorPanel';
import {DEMO_PORTFOLIO, initialState, workspaceReducer, validatePositions, holdingResearch} from './workspaceStore';
import {temporalView} from './temporalModel';
import './WorkspaceShell.css';
import MarketTape from './pythia/MarketTape.jsx';
import DiscoveryView from './pythia/DiscoveryView.jsx';
import MarketDesk, {SecuritySearch} from './pythia/MarketDesk.jsx';
import {NAVIGATION} from './pythia/deskClient.js';
import {ScopeIcon, PastIcon, ChartIcon, CloverIcon, GraphIcon} from './pythia/icons.jsx';
import './pythia/tokens.css';
import './pythia/shell.css';
const ICONS = [ScopeIcon, PastIcon, ChartIcon, CloverIcon, GraphIcon];
const AppContext = createContext(null);
const NOTICE = 'Historical simulation is descriptive evidence about the selected historical sample. It is NOT an expected return forecast and NOT an investment recommendation.';
const pct = value => typeof value === 'number' ? `${(value*100).toFixed(2)}%` : 'Unavailable';
function Value({metric}) { return <span title={metric?.reason}>{metric?.status === 'available' ? pct(metric.value) : metric?.reason ?? 'Not calculated'}</span>; }
async function calculate(path, payload) {
  const response = await fetch(`/api/portfolio/${path}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? 'Calculation unavailable');
  return result;
}
export default function WorkspaceShell() {
  const [state,dispatch] = useReducer(workspaceReducer, undefined, () => { try { return initialState(localStorage); } catch { return initialState(); } });
  const [ticker,setTicker] = useState('COHU');
  const [discoveryCandidate,setDiscoveryCandidate] = useState(null);
  const [theme,setTheme] = useState(() => {try {return localStorage.getItem('pythia:theme') ?? 'light';} catch {return 'light';}});
  useEffect(() => {document.documentElement.dataset.theme=theme;try {localStorage.setItem('pythia:theme',theme);} catch { /* optional preference */ }},[theme]);
  const [storageError,setStorageError] = useState('');
  const [analysis,setAnalysis] = useState(null), [simulation,setSimulation] = useState(null);
  const [performance,setPerformance] = useState(null);
  const [busy,setBusy] = useState(false), [gross,setGross] = useState(.02);
  useEffect(() => {
    try { localStorage.setItem('claimgraph:workspace:v1', JSON.stringify(state)); }
    catch { queueMicrotask(() => setStorageError('Browser storage full or unavailable. Export investigations to retain them.')); }
    if (location.pathname !== state.route) history.pushState(null,'',state.route);
  }, [state]);
  useEffect(() => { const pop = () => dispatch({type:'navigate',route:location.pathname}); window.addEventListener('popstate',pop); return () => window.removeEventListener('popstate',pop); }, []);
  const navigate = route => dispatch({type:'navigate',route});
  const snapshot = useCallback((id,patch) => dispatch({type:'snapshot',id,patch}), []);
  function open(candidate=null, simulationContext=null) {
    const id = crypto.randomUUID();
    dispatch({type:'open',workspace:{id,label:candidate?.pair ?? candidate?.ticker_a ?? 'Research',candidate,
      portfolio:{...state.portfolio,as_of:candidate?.requested_as_of ?? candidate?.signal_date ?? state.selected_as_of}, as_of:candidate?.requested_as_of ?? candidate?.signal_date ?? state.selected_as_of, simulation:simulationContext}});
  }
  async function selectCandidate(candidate) {
    dispatch({type:'candidate',candidate}); setSimulation(null); setPerformance(null);
    if (candidate) {
      const asOf = candidate.requested_as_of ?? candidate.signal_date;
      try { const result = await calculate('market',{tickers:[candidate.ticker_a,candidate.ticker_b],as_of:asOf}); setPerformance({pair:candidate.pair,as_of:asOf,result}); }
      catch(err) { setPerformance({pair:candidate.pair,as_of:asOf,result:{status:'unavailable',reason:err.message}}); }
    }
  }
  async function refresh() {
    setBusy(true); setAnalysis(null);
    try { setAnalysis(await calculate('analysis',{portfolio:state.portfolio,as_of:state.selected_as_of})); }
    catch(err) { setAnalysis({status:'unavailable',reason:err.message}); } finally { setBusy(false); }
  }
  async function simulate(candidate=state.candidate, asOf=state.selected_as_of) {
    dispatch({type:'candidate',candidate:{...candidate,requested_as_of:asOf}}); navigate('/explore'); setBusy(true); setSimulation(null);
    try { setSimulation(await calculate('simulate',{portfolio:{...state.portfolio,as_of:asOf},candidate,as_of:asOf,gross_overlay:gross})); }
    catch(err) { setSimulation({status:'unavailable',reason:err.message}); } finally { setBusy(false); }
  }
  const currentAnalysis = analysis?.as_of === state.selected_as_of && JSON.stringify(analysis?.portfolio) === JSON.stringify(state.portfolio) ? analysis : analysis?.status === 'unavailable' ? analysis : null;
  const currentSimulation = simulation?.status === 'unavailable' || (simulation?.as_of === state.selected_as_of && JSON.stringify(simulation?.portfolio) === JSON.stringify(state.portfolio) && simulation?.gross_overlay === gross && simulation?.candidate?.ticker_a === state.candidate?.ticker_a && simulation?.candidate?.ticker_b === state.candidate?.ticker_b) ? simulation : null;
  return <AppContext.Provider value={{state,dispatch}}><div className="research-shell">
    <header className="pythia-topbar"><div className="pythia-brand">PYTHIA<span>INVESTMENT INTELLIGENCE</span></div><div className="topbar-context">{ticker}<small>Evidence-led investment workspace</small></div><label>Research as of <input type="date" value={state.selected_as_of} onChange={e => {dispatch({type:'date',value:e.target.value});setSimulation(null);}} /></label><button onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')} aria-label="Toggle colour theme">{theme === 'light' ? 'Dark' : 'Light'}</button></header>
    <nav className="pythia-rail" aria-label="Main navigation">{NAVIGATION.map(([path,label],i) => {const Glyph=ICONS[i];return <button key={path} aria-current={state.route.startsWith(path) ? 'page' : undefined} onClick={() => navigate(path)}><Glyph/><span>{label}</span></button>;})}</nav>
    <div className="pythia-content">
    <nav className="browser-tabs" hidden={!state.route.startsWith('/investigate')} aria-label="Investigation workspaces">{state.workspaces.map(w => <span key={w.id}><button aria-pressed={state.route.endsWith(w.id)} onClick={() => navigate(`/investigate/${w.id}`)}>{w.label} investigation{w.model && ` · ${w.model.label ?? w.model.model}`}</button><button aria-label={`Close ${w.label}`} onClick={() => dispatch({type:'close',id:w.id})}>×</button></span>)}<button onClick={() => open()} aria-label="New investigation">New investigation +</button></nav>
    <section hidden={state.route !== '/now'}><MarketDesk active={state.route === '/now'} mode="now" ticker={ticker} onTicker={setTicker} asOf={state.selected_as_of} onAsOf={value => dispatch({type:'date',value})} portfolio={state.portfolio} onInvestigate={open}/></section>
    <section hidden={state.route !== '/past'}><MarketDesk discoveryCandidate={discoveryCandidate} active={state.route === '/past'} mode="past" ticker={ticker} onTicker={setTicker} asOf={state.selected_as_of} onAsOf={value => dispatch({type:'date',value})} portfolio={state.portfolio} onInvestigate={open}/></section>
    {state.route === '/investigate' && <section className="mode-page"><p className="eyebrow">CLAIMGRAPH / INVESTIGATIONS</p><h1>Follow the evidence.</h1><p>Open a saved example, or begin with a holding, security or anomaly. Inspect the graph, retrieve missing evidence, then prepare a report.</p><button onClick={() => open()}>New investigation +</button>{state.workspaces.map(w => <button key={w.id} onClick={() => navigate(`/investigate/${w.id}`)}>{w.label} investigation</button>)}</section>}
    {storageError && <p role="status">{storageError}</p>}
    <section hidden={state.route !== '/portfolio'} className="mode-page"><h1>{state.portfolio.name}</h1><p>{state.portfolio.positions.length} positions · As of {state.selected_as_of}</p>
      <PortfolioEditor portfolio={state.portfolio} onSave={portfolio => {dispatch({type:'portfolio',portfolio});setAnalysis(null);setSimulation(null);}} />
      <button disabled={busy} onClick={refresh}>{busy ? 'Calculating…' : 'Refresh analysis'}</button>
      {currentAnalysis?.status === 'unavailable' && <p role="status">Unavailable: {currentAnalysis.reason}</p>}
      {currentAnalysis?.status === 'available' && <><div className="metric-grid"><Metric label="20-session return" metric={currentAnalysis.return_20}/><Metric label="Annualised realised volatility" metric={currentAnalysis.summary.volatility}/><Metric label="Max drawdown" metric={currentAnalysis.summary.max_drawdown}/><div>Largest weight<strong>{pct(currentAnalysis.concentration.largest_weight)}</strong>HHI {currentAnalysis.concentration.hhi.toFixed(3)}</div></div>
        <Contributors values={currentAnalysis.contributions_20}/></>}
      <div className="table-scroll"><table><thead><tr>{['Holding','Weight','1d','5d','20d','63d','20d volatility','20d contribution','Research',''].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{state.portfolio.positions.map(p => {
        const research = holdingResearch(state.workspaces,p.ticker,state.selected_as_of), sec = currentAnalysis?.securities?.[p.ticker];
        const gaps = research.some(w => w.graph.nodes.some(n => ['missing_evidence','evidence_requirement'].includes(n.kind) && n.data?.resolution_status !== 'answered'));
        return <tr key={p.ticker}><td>{p.ticker}</td><td>{pct(p.weight)}</td>{[1,5,20,63].map(n => <td key={n}><Value metric={sec?.[`return_${n}`] ?? (sec?.status === 'unavailable' ? sec : null)}/></td>)}<td><Value metric={sec?.volatility_20}/></td><td>{pct(currentAnalysis?.contributions_20?.[p.ticker])}</td><td>{gaps ? 'Missing evidence unresolved · Follow-up available' : research.some(w => w.graph.followups?.length) ? 'Recent evidence added' : research.length ? 'Research available' : 'No recent investigation'}</td><td><button onClick={() => {setTicker(p.ticker);navigate('/past');}}>Market context</button><button onClick={() => open({mode:'holding',ticker_a:p.ticker,pair:p.ticker,signal_date:state.selected_as_of,requested_as_of:state.selected_as_of})}>Investigate</button></td></tr>;
      })}</tbody></table></div>
      <h2>Risk / questions and latest admitted research</h2><p>Existing holding-related evidence only. Investigate explicitly to retrieve BookReader, web and SEC information.</p>
      {state.portfolio.positions.map(p => <section key={p.ticker}><h3>{p.ticker}</h3>{holdingResearch(state.workspaces,p.ticker,state.selected_as_of).map(w => {
        const visible = temporalView(w.graph,`${state.selected_as_of}T23:59:59.999Z`);
        return <div key={w.id}><button onClick={() => navigate(`/investigate/${w.id}`)}>{w.label} · inspect research and provenance</button>{visible.nodes.filter(n => ['claim','document','missing_evidence','evidence_requirement'].includes(n.kind)).slice(-8).map(n => <p key={n.node_id}>{n.kind.replaceAll('_',' ')}: {n.label}</p>)}</div>;
      })}</section>)}
      <h2>Watched candidates</h2>{state.watched.map(c => <button key={c.pair} onClick={() => {selectCandidate(c);navigate('/explore');}}>{c.pair} · {c.signal_date}</button>)}
      <p>{NOTICE}</p>
    </section>
    <section hidden={state.route !== '/explore'} className="mode-page explore-page"><p className="eyebrow">DISCOVERY / THE INVESTMENT UNIVERSE</p><DiscoveryView asOf={state.selected_as_of} portfolio={state.portfolio} onInspect={(candidate,symbol) => {setDiscoveryCandidate(candidate);setTicker(symbol);navigate('/past');}}/><h2>Explore opportunities</h2><SecuritySearch onSelect={symbol => {setTicker(symbol);navigate('/past');}}/><p>Search the merged universe, examine a security, or scan relationships below. Membership labels describe current snapshots, not historical constituents.</p><p>{NOTICE}</p><DetectorPanel onSelectCandidate={selectCandidate} sharedAsOf={state.selected_as_of} onAsOf={value => dispatch({type:'date',value})}/>
      {state.candidate && <section className="candidate-detail"><h2>{state.candidate.pair}</h2><p>As of {state.candidate.requested_as_of ?? state.candidate.signal_date} · z {state.candidate.z_score ?? 'Unavailable'} · correlation {state.candidate.correlation ?? 'Unavailable'} · cointegration p {state.candidate.cointegration_p ?? 'Unavailable'}</p>
        <p>Formation history: {state.candidate.formation_start ?? 'Unavailable'} — {state.candidate.formation_end ?? 'Unavailable'}</p>
        {performance?.pair === state.candidate.pair && performance.as_of === state.selected_as_of && <MarketPerformance result={performance.result}/>}
        <p>Portfolio overlap: {state.portfolio.positions.filter(p => [state.candidate.ticker_a,state.candidate.ticker_b].includes(p.ticker)).map(p => `${p.ticker} ${pct(p.weight)}`).join(', ') || 'No directly held legs'}</p>
        <button onClick={() => open(state.candidate,currentSimulation?.status === 'available' ? {gross_overlay:gross} : null)}>Investigate</button><button onClick={() => dispatch({type:'watch',candidate:state.candidate})}>Watch in Portfolio</button>
        <label>Gross analytical overlay (%) <input type="number" min="0" max="100" step="0.5" value={gross*100} onChange={e => setGross(Number(e.target.value)/100)}/></label><button disabled={busy} onClick={() => simulate()}>Simulate against portfolio</button>
      </section>}
      {currentSimulation?.status === 'unavailable' && <p role="status">Simulation unavailable: {currentSimulation.reason}</p>}
      {currentSimulation?.status === 'available' && <section><h2>Historical simulation</h2><p>{currentSimulation.construction}</p><p>{currentSimulation.current.start} — {currentSimulation.current.end} · {currentSimulation.current.sessions} common sessions</p>
        <table><thead><tr><th>Sample</th><th>Return</th><th>Annualised volatility</th><th>Max drawdown</th></tr></thead><tbody>{[['current','Current portfolio'],['candidate_performance','Candidate scenario'],['combined','Portfolio + overlay']].map(([key,label]) => <tr key={key}><td>{label}</td><td><Value metric={currentSimulation[key].return_window}/></td><td><Value metric={currentSimulation[key].volatility}/></td><td><Value metric={currentSimulation[key].max_drawdown}/></td></tr>)}</tbody></table>
        <p>Candidate / portfolio correlation: {currentSimulation.correlation.status === 'available' ? currentSimulation.correlation.value.toFixed(3) : currentSimulation.correlation.reason}</p>
        <h3>Recent return decomposition</h3>{Object.entries(currentSimulation.securities).map(([t,s]) => <p key={t}>{t}: {[1,5,20,63].map(n => <span key={n}> {n}d <Value metric={s[`return_${n}`]}/></span>)}</p>)}
        <p>Missing evidence: {currentSimulation.remaining_question}</p><button onClick={() => open(state.candidate,{gross_overlay:gross})}>Investigate persistence and confounders</button><details><summary>Calculation / price provenance</summary><pre>{JSON.stringify(currentSimulation,null,2)}</pre></details></section>}
    </section>
    {state.workspaces.map(w => <section key={w.id} hidden={state.route !== `/investigate/${w.id}`} className="investigation-page"><Investigation workspace={w} onSnapshot={snapshot} onSimulate={(candidate,asOf) => simulate(candidate,asOf)}/></section>)}
    </div><MarketTape portfolio={state.portfolio} asOf={state.route === '/now' ? null : state.selected_as_of} onSelect={symbol => {setTicker(symbol);navigate('/now');}}/>
  </div></AppContext.Provider>;
}
function Metric({label,metric}) { return <div>{label}<strong><Value metric={metric}/></strong></div>; }
function PortfolioEditor({portfolio,onSave}) {
  const [text,setText] = useState(portfolio.positions.map(p => `${p.ticker} ${p.weight}`).join('\n'));
  const [name,setName] = useState(portfolio.name), [error,setError] = useState('');
  return <details><summary>Edit manual portfolio</summary><label>Name <input value={name} onChange={e => setName(e.target.value)}/></label><label>One ticker and decimal weight per line<textarea rows="5" value={text} onChange={e => setText(e.target.value)}/></label><button onClick={() => {try {onSave({...portfolio,name,positions:validatePositions(text)});setError('');} catch(err) {setError(err.message);}}}>Save holdings</button><button onClick={() => {setText(DEMO_PORTFOLIO.positions.map(p => `${p.ticker} ${p.weight}`).join('\n'));setName(DEMO_PORTFOLIO.name);}}>Load sample inputs</button>{error && <p role="alert">{error}</p>}</details>;
}

function MarketPerformance({result}) {
  if (result.status === 'unavailable') return <p>Market calculations unavailable: {result.reason}</p>;
  return <div><h3>Recent return decomposition</h3>{Object.entries(result.securities).map(([ticker,s]) => <p key={ticker}>{ticker}: {s.status === 'unavailable' ? s.reason : [1,5,20,63].map(n => <span key={n}> {n}d <Value metric={s[`return_${n}`]}/></span>)}</p>)}<p>A minus B: {[20,63].map(n => <span key={n}> {n}d {pct(result.relative_returns[n]?.value)} </span>)}</p></div>;
}

function Contributors({values}) {
  if (values.status === 'unavailable') return <p>{values.reason}</p>;
  const entries=Object.entries(values).sort((a,b) => b[1]-a[1]);
  return <><p>Largest positive contributors (20 sessions): {entries.filter(([,v]) => v > 0).slice(0,3).map(([t,v]) => `${t} ${pct(v)}`).join(' · ') || 'None in this sample'}</p><p>Largest negative contributors (20 sessions): {entries.filter(([,v]) => v < 0).reverse().slice(0,3).map(([t,v]) => `${t} ${pct(v)}`).join(' · ') || 'None in this sample'}</p></>;
}
