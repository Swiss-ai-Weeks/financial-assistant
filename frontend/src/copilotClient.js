export async function askCopilot(payload, signal) {
  const response = await fetch('/api/copilot', {method:'POST', signal, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(`${result.code ?? 'error'}: ${result.error}`);
  return result;
}
export function voiceAPIs(scope = globalThis) {
  return {Recognition:scope.SpeechRecognition ?? scope.webkitSpeechRecognition, synthesis:scope.speechSynthesis};
}
