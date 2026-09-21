import {useEffect, useState} from 'react';
import {progressRows} from './investigationClient.js';

export default function InvestigationProgress({status, context}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (status.state !== 'running') return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [status.state]);
  const end = status.state === 'running' ? now : Date.parse(status.updated_at);
  const seconds = Math.max(0, Math.floor((end - Date.parse(status.started_at)) / 1000)) || 0;
  const elapsed = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  return <section className="investigation-progress" aria-label="Investigation execution progress">
    <strong>INVESTIGATION {status.state.toUpperCase()} · {elapsed}</strong>
    <p>{context.provider} · {context.model}</p>
    {(context.mode === 'historical' || status.followup) && <p><strong>Evidence cutoff: {status.evidence_cutoff ?? `End of ${context.as_of} UTC`}</strong></p>}
    <ol aria-live="polite">{progressRows(status, context.mode === 'historical').map(row =>
      <li key={row.id} className={row.state}><span aria-label={row.state}>{row.symbol}</span><span>{row.label}</span><small>{row.detail}</small></li>)}</ol>
    <p>Current graph and review remain available below.</p>
  </section>;
}
