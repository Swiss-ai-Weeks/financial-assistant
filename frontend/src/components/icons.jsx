/* Stroke icons on a 24px grid, sized by the parent's font-size. */

function Icon({ children, size = 22 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const ChartIcon = (props) => (
  <Icon {...props}>
    <rect x="3.5" y="3.5" width="17" height="17" rx="1.5" />
    <path d="M8 16v-4M12 16V8M16 16v-6" />
  </Icon>
);

export const PastIcon = (props) => (
  <Icon {...props}>
    <path d="M4 12a8 8 0 1 0 2.6-5.9" />
    <path d="M4 4.5v4h4M12 8v4.5l3 1.8" />
  </Icon>
);

export const ScopeIcon = (props) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="7.5" />
    <circle cx="12" cy="12" r="2" />
    <path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4" />
  </Icon>
);

export const CloverIcon = (props) => (
  <Icon {...props}>
    <path d="M12 12c-1-4-6-4.5-6-1.2S10 14 12 12zM12 12c4-1 4.5-6 1.2-6S10 10 12 12zM12 12c1 4 6 4.5 6 1.2S14 10 12 12zM12 12c-4 1-4.5 6-1.2 6S14 14 12 12z" />
    <path d="M12 12c1 4 2 6 4 8.5" />
  </Icon>
);

export const GraphIcon = (props) => (
  <Icon {...props}>
    <circle cx="6" cy="6" r="2.2" />
    <circle cx="18" cy="6" r="2.2" />
    <circle cx="6" cy="18" r="2.2" />
    <circle cx="18" cy="18" r="2.2" />
    <path d="M8.2 6h7.6M6 8.2v7.6M18 8.2v7.6M8.2 18h7.6" />
  </Icon>
);

export const ChipIcon = (props) => (
  <Icon {...props}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="1.2" />
    <rect x="10" y="10" width="4" height="4" />
    <path d="M9 3.5v3M15 3.5v3M9 17.5v3M15 17.5v3M3.5 9h3M3.5 15h3M17.5 9h3M17.5 15h3" />
  </Icon>
);

export const SunIcon = (props) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="3.6" />
    <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6" />
  </Icon>
);

export const MoonIcon = (props) => (
  <Icon {...props}>
    <path d="M20 14.2A8 8 0 0 1 9.8 4a8 8 0 1 0 10.2 10.2z" />
  </Icon>
);

export const StarIcon = ({ filled, ...props }) => (
  <Icon {...props}>
    <path
      d="M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8z"
      fill={filled ? "currentColor" : "none"}
    />
  </Icon>
);

export const ChevronIcon = (props) => (
  <Icon {...props}>
    <path d="M6 9l6 6 6-6" />
  </Icon>
);

export const SearchIcon = (props) => (
  <Icon {...props}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.2-4.2" />
  </Icon>
);

export const PlusIcon = (props) => (
  <Icon {...props}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const CloseIcon = (props) => (
  <Icon {...props}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const ExternalIcon = (props) => (
  <Icon {...props}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Icon>
);

export const BoltIcon = (props) => (
  <Icon {...props}>
    <path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />
  </Icon>
);

const STRATEGY_GLYPHS = {
  vwap: (props) => (
    <Icon {...props}>
      <path d="M5 19V13M9.5 19V7M14 19V10M18.5 19V15" />
      <path d="M3.5 9.5c4-1 6-4.5 8.5-4.5s4 3.5 8.5 4" strokeDasharray="2 2.4" />
    </Icon>
  ),
  twap: (props) => (
    <Icon {...props}>
      <path d="M5 19v-8M9.5 19v-8M14 19v-8M18.5 19v-8" />
      <path d="M3.5 6.5h17" />
    </Icon>
  ),
  trend: (props) => (
    <Icon {...props}>
      <path d="M3.5 17c4 0 5-9 9-9s4 5 8 5" />
      <path d="M3.5 9c5 0 6 8 17 8" strokeDasharray="2 2.4" />
    </Icon>
  ),
  pairs: (props) => (
    <Icon {...props}>
      <path d="M3.5 9c3-3 5.5 3 8.5 0s5.5-3 8.5 0" />
      <path d="M3.5 15c3 3 5.5-3 8.5 0s5.5 5 8.5 2" />
    </Icon>
  ),
};

/** Glyph of a strategy monitor, used on the marketplace cards. */
export function StrategyIcon({ strategy, ...props }) {
  const Glyph = STRATEGY_GLYPHS[strategy];

  return Glyph ? <Glyph {...props} /> : null;
}
