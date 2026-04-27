/**
 * HTML escape helper. Used only for the few places where we actually need
 * to construct an HTML string (e.g. grammar long descriptions that allow
 * inline markup). Everything else goes through Svelte's auto-escaping
 * `{value}` interpolation.
 */
export function escapeHtml(s: string | number | null | undefined): string {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, (c) => {
    switch (c) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return c;
    }
  });
}
