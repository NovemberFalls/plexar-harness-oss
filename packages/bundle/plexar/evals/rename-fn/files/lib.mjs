export function fetchTotal(items) {
  return items.reduce((a, b) => a + b, 0);
}
