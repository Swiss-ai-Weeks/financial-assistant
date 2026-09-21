export function sourceHref(value, baseUrl) {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    if (baseUrl && value.startsWith(`${baseUrl}/documents/`)) {
      const id = decodeURIComponent(value.slice(`${baseUrl}/documents/`.length));
      if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$/.test(id) || id.includes('..')) return null;
      return `/api/bookreader/documents/${encodeURIComponent(id)}`;
    }
    return value;
  } catch { return null; }
}
