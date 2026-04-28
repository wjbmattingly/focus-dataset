// @ts-check
import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";

// GitHub Pages serves the site at /focus-dataset/ when there is no custom
// domain. Override the base via SITE_BASE in CI if you ever rename the repo.
const repoBase = process.env.SITE_BASE ?? "/focus-dataset/";

export default defineConfig({
  site: "https://wjbmattingly.github.io",
  base: repoBase,
  trailingSlash: "ignore",
  integrations: [mdx()],
});
