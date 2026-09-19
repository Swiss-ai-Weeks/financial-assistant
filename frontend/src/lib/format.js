export function price(value) {
  if (value == null) return "—";

  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function signed(value, digits = 2) {
  if (value == null) return "—";

  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function percent(value, digits = 2) {
  return value == null ? "—" : `${signed(value, digits)}%`;
}

export function compact(value) {
  if (value == null) return "—";

  return Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function money(value) {
  if (value == null) return "—";

  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function tone(value) {
  if (value == null || value === 0) return "";

  return value > 0 ? "up" : "down";
}

export function shortDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function dateTime(iso) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
}

/** Calendar day (UTC) of a timestamp, as YYYY-MM-DD. */
export function dayOf(iso) {
  return new Date(iso).toISOString().slice(0, 10);
}
