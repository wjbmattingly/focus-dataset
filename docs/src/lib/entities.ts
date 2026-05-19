import type { CollectionEntry } from "astro:content";

export type EntityKind = "people" | "places" | "organizations" | "sources";

export interface RawEntity {
  name: string;
  canonical?: string | null;
}

export interface SectionRef {
  /** Issue id, e.g. "Issue 01" */
  issueId: string;
  /** Issue Astro entry id (slug), e.g. "Issue-01" */
  issueSlug: string;
  /** Issue display name */
  issueName: string;
  /** Section index 0-based within the issue */
  sectionId: string;
  sectionTitle: string;
  sectionType: "front_matter" | "article" | "end_matter";
  sectionUrlSlug: string;
  pageStart: number;
  pageEnd: number;
}

export interface EntityMention extends SectionRef {
  /** The literal surface form the LLM tagged in this section */
  surface: string;
}

export interface EntityRecord {
  slug: string;
  kind: EntityKind;
  /** Best display name (canonical preferred, else most common surface form). */
  display: string;
  /** Distinct surface forms ever used for this entity. */
  surfaces: string[];
  mentions: EntityMention[];
}

const ENTITY_KINDS: EntityKind[] = ["people", "places", "organizations", "sources"];

/** Stable url slug for an entity name (canonical or surface). */
export function entitySlug(name: string): string {
  return (
    name
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "") // strip diacritics
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "unknown"
  );
}

/** The "key" we group by: canonical if set, otherwise the surface form. */
function entityKey(e: RawEntity): string {
  return (e.canonical && e.canonical.trim()) || e.name.trim();
}

export function buildEntityIndex(
  issues: CollectionEntry<"issues">[]
): Record<EntityKind, Map<string, EntityRecord>> {
  const idx: Record<EntityKind, Map<string, EntityRecord>> = {
    people: new Map(),
    places: new Map(),
    organizations: new Map(),
    sources: new Map(),
  };

  for (const issue of issues) {
    const data = issue.data;
    for (const section of data.sections) {
      const ref = {
        issueId: data.issue_id,
        issueSlug: issue.id,
        issueName: data.issue_name,
        sectionId: section.section_id,
        sectionTitle: section.title,
        sectionType: section.section_type,
        sectionUrlSlug: section.url_slug,
        pageStart: section.page_start,
        pageEnd: section.page_end,
      };

      for (const kind of ENTITY_KINDS) {
        const list: RawEntity[] | undefined = (section as any)[kind];
        if (!list) continue;
        for (const ent of list) {
          const key = entityKey(ent);
          if (!key) continue;
          const slug = entitySlug(key);
          let rec = idx[kind].get(slug);
          if (!rec) {
            rec = {
              slug,
              kind,
              display: key,
              surfaces: [],
              mentions: [],
            };
            idx[kind].set(slug, rec);
          }
          if (!rec.surfaces.includes(ent.name)) rec.surfaces.push(ent.name);
          rec.mentions.push({ ...ref, surface: ent.name });
        }
      }
    }
  }

  return idx;
}

export function entityUrl(kind: EntityKind, slug: string): string {
  return `/${kind}/${slug}`;
}

/** Escape HTML special characters. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

interface HighlightTarget {
  surface: string;
  kind: EntityKind;
  slug: string;
  /** Display label (canonical) used in the link aria. */
  display: string;
}

/**
 * Mutable counter + lookup table shared across every paragraph in a section.
 * Each time `highlightBody` matches a source surface form it bumps the counter,
 * emits the marker with `id="cite-N"`, and records the FIRST anchor seen for
 * that surface in `anchors` (so the sidebar can deep-link to it).
 */
export interface SourceAnchorState {
  /** Monotonic counter; the next id will be `cite-${counter}`. */
  counter: number;
  /** Map from source surface form to the first anchor id assigned to it. */
  anchors: Map<string, string>;
}

export function makeSourceAnchorState(): SourceAnchorState {
  return { counter: 0, anchors: new Map() };
}

/**
 * Wrap mentions of every entity in `entities` inside `<a class="entity-mark
 * entity-mark--<kind>" href="/<kind>/<slug>">…</a>` spans. Longer surfaces are
 * matched first so "Nelson Mandela" wins over "Mandela". Each character is
 * tagged at most once. The returned string is HTML and should be rendered
 * with `set:html`.
 *
 * If a bucket has `kind === "sources"`, those matches are rendered with an
 * `id="cite-N"` and `href="#cite-N"` anchor (so a sidebar source list can
 * scroll to the in-body citation) and tracked in `sourceState.anchors`.
 */
export function highlightBody(
  body: string,
  buckets: { kind: EntityKind; entities: RawEntity[] }[],
  baseUrl: (path: string) => string,
  sourceState?: SourceAnchorState
): string {
  const targets: HighlightTarget[] = [];
  for (const bucket of buckets) {
    for (const ent of bucket.entities) {
      const display = entityKey(ent);
      const slug = entitySlug(display);
      const surface = ent.name;
      if (!surface) continue;
      targets.push({ surface, kind: bucket.kind, slug, display });
      // For non-source entities, also highlight the canonical form when it's
      // distinct. We skip this for sources: the canonical name (e.g. "The
      // Guardian, London") generally does not appear in the article prose,
      // and matching it could create misleading citation anchors.
      if (display !== surface && bucket.kind !== "sources") {
        targets.push({ surface: display, kind: bucket.kind, slug, display });
      }
    }
  }
  // De-dupe (surface, kind) pairs and sort longest first so multi-word names
  // get matched before their substrings.
  const seen = new Set<string>();
  const dedup: HighlightTarget[] = [];
  for (const t of targets) {
    const key = `${t.kind}|${t.surface}`;
    if (seen.has(key)) continue;
    seen.add(key);
    dedup.push(t);
  }
  dedup.sort((a, b) => b.surface.length - a.surface.length);

  // Build a single combined regex with alternation, but we still need to map
  // matches back to the right target, so iterate per target with a "claimed"
  // bitmap to avoid double-tagging.
  const claimed = new Uint8Array(body.length);
  type Marker = {
    start: number;
    end: number;
    kind: EntityKind;
    slug: string;
    display: string;
    surface: string;
  };
  const markers: Marker[] = [];

  for (const t of dedup) {
    if (t.surface.length < 2) continue;
    const isWordy = /^[\w].*[\w]$/.test(t.surface);
    const flags = "g";
    const pattern = isWordy
      ? new RegExp(`\\b${escapeRegex(t.surface)}\\b`, flags)
      : new RegExp(escapeRegex(t.surface), flags);
    let m: RegExpExecArray | null;
    while ((m = pattern.exec(body)) !== null) {
      const start = m.index;
      const end = start + m[0].length;
      let conflict = false;
      for (let i = start; i < end; i++) {
        if (claimed[i]) {
          conflict = true;
          break;
        }
      }
      if (conflict) continue;
      for (let i = start; i < end; i++) claimed[i] = 1;
      markers.push({
        start,
        end,
        kind: t.kind,
        slug: t.slug,
        display: t.display,
        surface: t.surface,
      });
    }
  }

  markers.sort((a, b) => a.start - b.start);

  let out = "";
  let cursor = 0;
  for (const mk of markers) {
    if (mk.start < cursor) continue;
    out += escapeHtml(body.slice(cursor, mk.start));
    const surface = body.slice(mk.start, mk.end);
    if (mk.kind === "sources") {
      // Sources get anchor IDs so the sidebar can scroll to them. Without a
      // state object we fall back to a plain marker (e.g. inside the heading
      // highlighter where we don't care about anchors).
      if (sourceState) {
        sourceState.counter += 1;
        const id = `cite-${sourceState.counter}`;
        if (!sourceState.anchors.has(mk.surface)) {
          sourceState.anchors.set(mk.surface, id);
        }
        out += `<a class="entity-mark entity-mark--sources" id="${id}" href="#${id}" title="${escapeHtml(mk.display)}">${escapeHtml(surface)}</a>`;
      } else {
        out += `<span class="entity-mark entity-mark--sources" title="${escapeHtml(mk.display)}">${escapeHtml(surface)}</span>`;
      }
    } else {
      const href = baseUrl(`/${mk.kind}/${mk.slug}`);
      out += `<a class="entity-mark entity-mark--${mk.kind}" href="${href}" title="${escapeHtml(mk.display)}">${escapeHtml(surface)}</a>`;
    }
    cursor = mk.end;
  }
  out += escapeHtml(body.slice(cursor));
  return out;
}

/** Split a string into paragraphs on blank lines. */
export function paragraphs(text: string): string[] {
  return String(text || "")
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/* ------------------------------------------------------------------ */
/* Lightweight markdown rendering for section bodies                  */
/* ------------------------------------------------------------------ */
/**
 * The bodies that Gemini emits use a tiny subset of markdown that the dots.ocr
 * layout already encodes (section headings as `#`/`##`/`###`, bold leading
 * terms as `**term**`, and bullet lists as `* item`). We render that subset
 * inline so the article doesn't end up displaying literal `#` characters.
 * Anything else falls back to plain paragraph rendering.
 */

export type BodyBlock =
  | { kind: "heading"; level: 2 | 3 | 4; html: string }
  | { kind: "paragraph"; html: string }
  | { kind: "list"; items: string[] };

export interface ParsedBody {
  blocks: BodyBlock[];
  /** First in-body anchor id assigned to each source surface form. */
  sourceAnchors: Map<string, string>;
}

/** Wrap entity mentions, then convert any surviving `**text**` to <strong>. */
function renderInline(
  text: string,
  buckets: { kind: EntityKind; entities: RawEntity[] }[],
  baseUrl: (path: string) => string,
  sourceState?: SourceAnchorState
): string {
  const highlighted = highlightBody(text, buckets, baseUrl, sourceState);
  // Bold markers survive `escapeHtml` (it doesn't touch `*`) so we can promote
  // them after the fact. The negative class `[^*]` avoids gobbling across an
  // adjacent `**` boundary.
  return highlighted.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
}

/**
 * Parse a section body into a sequence of headings / paragraphs / lists, with
 * entity-link HTML already embedded in each block. Consumers just need to
 * render each block in the matching element.
 *
 * If `buckets` includes a `sources` bucket, every matched source citation is
 * wrapped with an `id="cite-N"` anchor in the body and recorded in the
 * returned `sourceAnchors` map (surface form -> first anchor id) so the
 * sidebar can render deep links.
 */
export function parseBodyToBlocks(
  body: string,
  buckets: { kind: EntityKind; entities: RawEntity[] }[],
  baseUrl: (path: string) => string
): ParsedBody {
  const out: BodyBlock[] = [];
  const paras = paragraphs(body);
  const sourceState = makeSourceAnchorState();

  for (const p of paras) {
    // Heading? Single-line paragraph that starts with 1-4 `#` followed by space.
    const headingMatch = !p.includes("\n") && p.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = Math.min(4, headingMatch[1].length + 1) as 2 | 3 | 4;
      out.push({
        kind: "heading",
        level,
        // Headings don't carry citations; pass no source state so any stray
        // source-shaped substring won't claim an anchor id.
        html: renderInline(headingMatch[2].trim(), buckets, baseUrl),
      });
      continue;
    }

    // List item? Whole paragraph is one `* item` (possibly multi-line).
    const listMatch = p.match(/^[*-]\s+([\s\S]+)$/);
    if (listMatch) {
      const itemHtml = renderInline(listMatch[1].trim(), buckets, baseUrl, sourceState);
      const last = out[out.length - 1];
      if (last && last.kind === "list") {
        last.items.push(itemHtml);
      } else {
        out.push({ kind: "list", items: [itemHtml] });
      }
      continue;
    }

    // Plain paragraph.
    out.push({ kind: "paragraph", html: renderInline(p, buckets, baseUrl, sourceState) });
  }

  return { blocks: out, sourceAnchors: sourceState.anchors };
}
