import {useEffect, useState} from 'react';
import {deskRequest} from './deskClient.js';
export default function MarketTape({portfolio, asOf, onSelect}) {
  const [result,setResult] = useState(null);
  const tickers=portfolio.positions.map(p => p.ticker).join(',');
  const key=`${tickers}:${asOf}`;
  useEffect(() => {
    const controller=new AbortController();
    deskRequest('/api/market/tape',{tickers,as_of:asOf},controller.signal)
      .then(data => setResult({key,...data})).catch(() => { /* Quote availability never blocks navigation. */ });
    return () => controller.abort();
  },[tickers,asOf,key]);
  const current=result?.key === key ? result : null;
  return <footer className="pythia-tape"><span>YOUR BOOK</span>{portfolio.positions.map(p => {
    const quote=current?.quotes?.find(q => q.ticker === p.ticker);
    const value=quote?.return_1?.value;
    return <button key={p.ticker} onClick={() => onSelect(p.ticker)} title={`Market as of ${current?.as_of ?? asOf ?? 'latest cache'} · ${quote?.reason ?? quote?.return_1?.reason ?? '1-session return'}`}>{p.ticker} <small>{(p.weight*100).toFixed(1)}% weight</small><small style={{color:value == null ? undefined : value >= 0 ? 'var(--up)' : 'var(--down)'}}>{value == null ? ' · market —' : ` · ${value >= 0 ? '+' : ''}${(value*100).toFixed(2)}%`}</small></button>;
  })}<span className="tape-status">{current?.as_of ?? 'Market cache'} · ClaimGraph research</span></footer>;
}
