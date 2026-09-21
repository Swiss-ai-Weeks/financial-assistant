export const NAVIGATION = [
  ['/now','Now'], ['/past','Past'], ['/portfolio','Portfolio'], ['/explore','Explore'], ['/investigate','Investigate'],
];
export async function deskRequest(path, params={}, signal) {
  const response = await fetch(`${path}?${new URLSearchParams(Object.entries(params).filter(([,v]) => v != null))}`,{signal});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? 'Market context unavailable');
  return body;
}
export function holdingCandidate(ticker, asOf) {
  return {mode:'security',ticker_a:ticker,pair:ticker,signal_date:asOf,requested_as_of:asOf};
}
