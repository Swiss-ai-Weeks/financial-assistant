import { useEffect, useRef, useState } from 'react';
import { askCopilot, voiceAPIs } from './copilotClient.js';

export default function CopilotPanel({context, model, onAction, onInvestigate, graph, disabled}) {
  const [question,setQuestion] = useState(''), [reply,setReply] = useState(null), [status,setStatus] = useState('');
  const [route,setRoute] = useState('interaction'), [speak,setSpeak] = useState(false), [error,setError] = useState('');
  const controller = useRef(null), recognition = useRef(null);
  const {Recognition,synthesis} = voiceAPIs();
  useEffect(() => () => {controller.current?.abort(); recognition.current?.abort(); synthesis?.cancel();}, [synthesis]);
  async function ask(event) {
    event.preventDefault(); setStatus('Thinking…'); setError('');
    controller.current?.abort(); controller.current = new AbortController();
    try {
      const result = await askCopilot({question, route, context, analysis_model:model}, controller.current.signal);
      setReply(result); onAction(result.ui_action); setStatus('');
      if (speak && synthesis && globalThis.SpeechSynthesisUtterance) {
        const utterance = new SpeechSynthesisUtterance(result.answer);
        utterance.onend = () => setStatus(''); utterance.onerror = () => setStatus('');
        setStatus('Speaking…'); synthesis.speak(utterance);
      }
    } catch (err) {if (err.name !== 'AbortError') {setError(err.message);setStatus('');}}
  }
  const target = graph.nodes.find(n => n.node_id === reply?.analysis_request?.target_node_id);
  return <details className="copilot-panel"><summary>Copilot · advisory assistance</summary>
    <small>{reply ? `${reply.route} · ${reply.model.label} · ${reply.model.locality}` : `Workspace analysis · ${model?.label ?? model?.model ?? 'No model selected'}`}</small>
    <form onSubmit={ask}><label>Request plane <select value={route} onChange={e => setRoute(e.target.value)}><option value="interaction">Interaction</option><option value="analysis">Analysis commentary</option><option value="frontier">Frontier comparison (external egress)</option></select></label>
      <label>Ask about this view<input value={question} maxLength={2000} onChange={e => setQuestion(e.target.value)} placeholder="What am I looking at?" /></label>
      <button type="button" disabled={!Recognition || status === 'Thinking…'} onClick={() => {
        try {recognition.current?.abort(); const r = new Recognition(); recognition.current = r;
          r.onresult = e => setQuestion(e.results[0][0].transcript); r.onend = () => setStatus('');
          r.onerror = () => {setStatus('');setError('Speech recognition unavailable; please type.');};
          r.start();setStatus('Listening…');
        } catch {setError('Speech recognition unavailable; please type.');}
      }}>Microphone</button><button disabled={!question.trim() || status === 'Thinking…'}>Ask</button>
      {!Recognition && <small>Voice input unavailable in this browser</small>}
      {synthesis && <label><input type="checkbox" checked={speak} onChange={e => setSpeak(e.target.checked)} /> Speak responses</label>}
    </form><p role="status">{status}</p>{error && <p role="alert">{error}</p>}
    {reply && <><p><strong>{reply.route === 'interaction' ? 'UI assistance' : `${reply.route} commentary`} · not admitted evidence</strong></p><p>{reply.answer}</p>
      {reply.ui_action && <small>UI action: {reply.ui_action.type}</small>}
      {['missing_evidence','evidence_requirement'].includes(target?.kind) && <button disabled={disabled} onClick={() => onInvestigate(target.node_id)}>Run existing missing-evidence investigation</button>}
      <details><summary>Execution / routing</summary><pre>{JSON.stringify(reply.executions ?? reply.execution,null,2)}</pre></details></>}
  </details>;
}
