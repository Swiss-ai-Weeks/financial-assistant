import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";

const PLANES = [
  ["interaction", "Navigate"],
  ["analysis", "Analyse"],
  ["frontier", "Second opinion"],
];

const OPEN_KINDS = ["missing_evidence", "evidence_requirement"];

function voice() {
  return {
    Recognition: globalThis.SpeechRecognition ?? globalThis.webkitSpeechRecognition,
    synthesis: globalThis.speechSynthesis,
  };
}

/**
 * Chat over one ClaimGraph view.
 *
 * It explains what is on screen and may move the view: select
 * a node, filter, fit. It can never add evidence or change a
 * relation. What it says is commentary, labelled as such, and
 * when it suggests researching an open question a person has
 * to press the button that starts the existing follow-up.
 */
export default function CopilotPanel({
  buildContext,
  graph,
  modelId,
  modelLabel,
  followUp,
  onAction,
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [plane, setPlane] = useState("interaction");
  const [thread, setThread] = useState([]);
  const [status, setStatus] = useState(null);
  const [speak, setSpeak] = useState(false);

  const controller = useRef(null);
  const recognition = useRef(null);

  const { Recognition, synthesis } = voice();

  useEffect(
    () => () => {
      controller.current?.abort();
      recognition.current?.abort();
      synthesis?.cancel();
    },
    [synthesis]
  );

  const ask = async (event) => {
    event.preventDefault();

    const asked = question.trim();

    if (!asked) return;

    controller.current?.abort();
    controller.current = new AbortController();

    setStatus("Thinking…");
    setThread((items) => [...items, { role: "you", text: asked }]);
    setQuestion("");

    try {
      const reply = await api.copilot(
        { question: asked, route: plane, context: buildContext(), model_id: modelId },
        controller.current.signal
      );

      let applied = null;

      try {
        onAction(reply.ui_action);
        applied = reply.ui_action?.type !== "none" ? reply.ui_action?.type : null;
      } catch (problem) {
        applied = `refused: ${problem.message}`;
      }

      setThread((items) => [...items, { role: "copilot", reply, applied }]);
      setStatus(null);

      if (speak && synthesis && globalThis.SpeechSynthesisUtterance) {
        synthesis.speak(new SpeechSynthesisUtterance(reply.answer));
      }
    } catch (error) {
      if (error.name === "AbortError") return;

      setThread((items) => [...items, { role: "error", text: error.message }]);
      setStatus(null);
    }
  };

  const listen = () => {
    try {
      recognition.current?.abort();

      const session = new Recognition();

      recognition.current = session;
      session.onresult = (event) => setQuestion(event.results[0][0].transcript);
      session.onend = () => setStatus(null);
      session.onerror = () => setStatus(null);
      session.start();

      setStatus("Listening…");
    } catch {
      setStatus(null);
    }
  };

  if (!open) {
    return (
      <button className="copilot__launcher" onClick={() => setOpen(true)}>
        <span className="eyebrow">Copilot</span>
        Ask about this graph
      </button>
    );
  }

  return (
    <section className="copilot" aria-label="ClaimGraph Copilot">
      <header className="copilot__header">
        <div>
          <span className="eyebrow">Copilot · advisory</span>
          <small className="muted mono">{modelLabel ?? "default model"}</small>
        </div>
        <button className="inspector__close" onClick={() => setOpen(false)} aria-label="Close Copilot">
          ✕
        </button>
      </header>

      <div className="copilot__thread">
        {thread.length === 0 && (
          <p className="muted">
            Try “What am I looking at?”, “Show what counters the first
            explanation”, or select an open question and ask to investigate it.
            Answers are commentary, never evidence.
          </p>
        )}

        {thread.map((item, index) => {
          if (item.role === "you") {
            return (
              <p key={index} className="copilot__you">
                {item.text}
              </p>
            );
          }

          if (item.role === "error") {
            return (
              <div key={index} className="error-banner">
                {item.text}
              </div>
            );
          }

          const target = graph.nodes.find(
            (node) => node.node_id === item.reply.analysis_request?.target_node_id
          );

          return (
            <div key={index} className="copilot__reply">
              <small className="muted mono">
                {item.reply.route} · {item.reply.model.label} ·{" "}
                {item.reply.model.local ? "local" : "external"} · not admitted evidence
              </small>

              <p>{item.reply.answer}</p>

              {item.applied && <small className="muted mono">view: {item.applied}</small>}

              {target && OPEN_KINDS.includes(target.kind) && (
                <button
                  className="btn btn--small"
                  disabled={!followUp || followUp.disabled}
                  title={followUp?.reason}
                  onClick={() => followUp.start(target.node_id)}
                >
                  Research “{target.label.slice(0, 60)}”
                </button>
              )}

              <details>
                <summary>Execution</summary>
                <pre className="inspector-json">
                  {JSON.stringify(item.reply.executions ?? item.reply.execution, null, 2)}
                </pre>
              </details>
            </div>
          );
        })}

        {status && <p className="muted mono">{status}</p>}
      </div>

      <form className="copilot__form" onSubmit={ask}>
        <div className="copilot__planes">
          {PLANES.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`graph-filters__chip ${plane === key ? "is-active" : ""}`}
              title={
                key === "frontier"
                  ? "Only on request: the view is sent to the external comparison model"
                  : undefined
              }
              onClick={() => setPlane(key)}
            >
              {label}
            </button>
          ))}

          {synthesis && (
            <label className="copilot__speak muted">
              <input
                type="checkbox"
                checked={speak}
                onChange={(event) => setSpeak(event.target.checked)}
              />
              speak
            </label>
          )}
        </div>

        <div className="copilot__input">
          <input
            value={question}
            maxLength={2000}
            placeholder="Ask about this view…"
            onChange={(event) => setQuestion(event.target.value)}
          />
          {Recognition && (
            <button type="button" className="btn btn--ghost btn--small" onClick={listen}>
              Mic
            </button>
          )}
          <button className="btn btn--small" disabled={!question.trim() || status === "Thinking…"}>
            Ask
          </button>
        </div>
      </form>
    </section>
  );
}
