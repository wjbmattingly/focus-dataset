import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const entity = z.object({
  name: z.string(),
  canonical: z.string().nullable().optional(),
});

const section = z.object({
  section_id: z.string(),
  section_type: z.enum(["front_matter", "article", "end_matter"]),
  title: z.string(),
  summary: z.string(),
  body: z.string(),
  page_start: z.number().int(),
  page_end: z.number().int(),
  people: z.array(entity).default([]),
  places: z.array(entity).default([]),
  organizations: z.array(entity).default([]),
  url_slug: z.string(),
});

const page = z.object({
  page_id: z.string(),
  page_number: z.number().int(),
  image: z.string(), // relative path under /public, e.g. /page-images/Issue 01/Issue 1_page_001.webp
  width: z.number().int().optional(),
  height: z.number().int().optional(),
});

const issues = defineCollection({
  loader: glob({ pattern: "**/*.json", base: "./src/content/issues" }),
  schema: z.object({
    issue_id: z.string(),
    issue_name: z.string(),
    parent_folder: z.string().nullable().optional(),
    issue_title: z.string().nullable().optional(),
    issue_summary: z.string(),
    num_pages: z.number().int(),
    is_validated: z.boolean(),
    pages: z.array(page),
    sections: z.array(section),
  }),
});

export const collections = { issues };
