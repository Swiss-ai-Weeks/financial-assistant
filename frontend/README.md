# Pythia — frontend

React + Vite. Talks to the FastAPI service through `/api` (proxied to
`http://127.0.0.1:8080` in development).

```bash
npm install
npm run dev      # http://localhost:5173
npm run lint
npm run build    # output in dist/, served by the API in production
```

## Layout

```
src/
  api/client.js          every HTTP call the UI makes
  hooks/                 useResource (keyed fetching), useInvestigation (polling), useTheme
  lib/                   number/date formatting, strategy presentation metadata
  styles/                tokens.css holds every colour; light and dark are two token sets
  components/
    layout/              top bar, icon rail, tabs, ticker tape
    chart/               candles + strategy overlays + anomaly markers, pair spread
    portfolio/           symbol search, performance strip, positions
    anomalies/           blotter, strategy monitor marketplace, pair scan result
    news/                ticker wire, book wire
    investigation/       explain panel, stages, verdicts, claims, ClaimGraph view
  App.jsx                desk state and composition
```

Behind a reverse proxy (NVIDIA Launchpad), set `VITE_HMR_HOST` to the public
hostname so hot reload connects back over `wss`.
