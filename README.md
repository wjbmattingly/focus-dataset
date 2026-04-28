# focus-dataset

Tooling and datasets built from the corrected dots.ocr output of *FOCUS on Political Repression in Southern Africa*, the news bulletin of the International Defence & Aid Fund (1975-1990s).

This repo produces two datasets on the [bitter-aloe](https://huggingface.co/bitter-aloe) Hugging Face org:

- [`bitter-aloe/focus-raw-ocr`](https://huggingface.co/datasets/bitter-aloe/focus-raw-ocr) – page-level: image, document, page, corrected layout JSON.
- [`bitter-aloe/focus-processed-articles`](https://huggingface.co/datasets/bitter-aloe/focus-processed-articles) – issue-level: page images, full layout, and a Gemini-extracted sequence of articles / front-matter / end-matter with people, places, and organizations.

It also contains a static GitHub Pages site (under `docs/`) for searching the processed articles.

## Layout

```
focus-dataset/
├── docs/                       # Astro site that ships to GitHub Pages
│   ├── astro.config.mjs        # base = /focus-dataset/
│   ├── package.json            # build = `astro build && pagefind --site dist`
│   ├── public/page-images/     # downscaled webp page renders (gitignored shards)
│   └── src/
│       ├── components/         # SiteLayout, Header, Footer, EntityBlock
│       ├── content/issues/     # one JSON per issue (output of export_for_site.py)
│       ├── pages/              # /, /issues, /issues/[slug], /issues/[slug]/[section], /search, /about
│       └── styles/             # theme + focus.css (palette borrowed from personal-website)
├── .github/workflows/deploy.yml
├── scripts/
│   ├── build_raw_ocr.py        # Build & push focus-raw-ocr
│   ├── process_issue.py        # Run Gemini on one issue (test harness)
│   ├── build_articles.py       # Build & push focus-processed-articles
│   └── export_for_site.py      # Turn extractions into docs/src/content/issues/*.json
├── src/focus_dataset/
│   ├── data.py                 # Scanner over the corrected dots.ocr export
│   ├── gemini.py               # Gemini 3.1 Flash Lite Preview wrapper
│   └── schema.py               # Pydantic models for the article output
├── requirements.txt
└── .env                        # GEMINI_API_KEY=...
```

## Source data

By default the scripts expect:

- `--corrected-dir` — corrected dots.ocr export (e.g. `~/Downloads/entire_project_2026-03-24T152159`).
  Each page is a pair `<page_name>.json` + `<page_name>_metadata.json`.
- `--images-dir` — original page renders, e.g. `~/Downloads/focus_output`. Image files are
  located using the `folder_name` field in the metadata sidecar.

## Quickstart — datasets

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build & push the page-level dataset (~3 minutes)
python scripts/build_raw_ocr.py \
  --corrected-dir ~/Downloads/entire_project_2026-03-24T152159 \
  --images-dir   ~/Downloads/focus_output \
  --push

# Test Gemini on Issue 01 only (~1 minute)
python scripts/process_issue.py --issue "Issue 01"

# Build & push the issue-level processed dataset
python scripts/build_articles.py \
  --corrected-dir ~/Downloads/entire_project_2026-03-24T152159 \
  --images-dir   ~/Downloads/focus_output \
  --push
```

## Quickstart — website

The site is a vanilla Astro project under `docs/` with [Pagefind](https://pagefind.app)
for static client-side search. It deploys via the `Build and deploy site to GitHub Pages`
workflow in `.github/workflows/deploy.yml`.

```bash
# 1. Export one or more processed issues into the site.
python scripts/export_for_site.py --only "Issue 01"

# 2. Run locally
cd docs
npm install
npm run dev          # http://localhost:4321/focus-dataset/

# 3. Build + index for production
npm run build        # writes dist/ + dist/pagefind/
npm run preview
```

To deploy:

1. Push `main` to GitHub.
2. Open **Settings → Pages** on the repo and set **Source: GitHub Actions**.
3. The next push (or a manual `Run workflow`) builds the site and publishes it
   at <https://wjbmattingly.github.io/focus-dataset/>. The action only fires
   when `docs/**` or the workflow itself changes.

If the repo is ever renamed, set the `SITE_BASE` env var in the workflow to
match (e.g. `SITE_BASE: /new-name/`).

## License

The code is MIT-licensed. The underlying *FOCUS* archive content is © the
International Defence & Aid Fund and its successors; the corrected transcriptions
and structured extractions in these datasets are released by The Bitter Aloe
Project for non-commercial research use. See the dataset cards on Hugging Face
for full terms.
