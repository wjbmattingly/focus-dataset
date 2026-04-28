/**
 * Site metadata and copy. Edit this file to re-skin the front-end.
 * Theme tokens live in `src/styles/theme.css`.
 */
export const site = {
  title: "FOCUS Archive",
  shortTitle: "FOCUS",
  description:
    "A searchable archive of FOCUS on Political Repression in Southern Africa, the news bulletin of the International Defence & Aid Fund (1975-1990s).",
  url: "https://wjbmattingly.github.io/focus-dataset",
  org: "The Bitter Aloe Project",
  orgUrl: "https://huggingface.co/bitter-aloe",
} as const;

export const datasets = [
  {
    label: "focus-raw-ocr",
    href: "https://huggingface.co/datasets/bitter-aloe/focus-raw-ocr",
    blurb: "Page-level corrected dots.ocr layouts joined to the original page renders.",
  },
  {
    label: "focus-processed-articles",
    href: "https://huggingface.co/datasets/bitter-aloe/focus-processed-articles",
    blurb: "Issue-level structured extractions: articles, summaries, and per-section people, places, and organizations.",
  },
] as const;

export const social = [
  { name: "Hugging Face", href: "https://huggingface.co/bitter-aloe" },
  { name: "GitHub", href: "https://github.com/wjbmattingly/focus-dataset" },
] as const;
