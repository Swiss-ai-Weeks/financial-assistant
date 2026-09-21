export function sessionNews(items, day) {
  return (items ?? []).filter(item => !day || item.published_at.slice(0, 10) === day);
}
