const base = import.meta.env.BASE_URL;

/**
 * Prefix a path with the site's configured base. Pass site-absolute paths
 * like "/issues" or "/images/foo.png". External URLs and mailto/tel links are
 * returned unchanged.
 */
export function url(path: string): string {
  if (!path) return base;
  if (/^(https?:|mailto:|tel:|#)/.test(path)) return path;
  const trimmedBase = base.endsWith("/") ? base.slice(0, -1) : base;
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${trimmedBase}${clean}`;
}
