# hooksmith marketing site

Static landing page for **hooksmith.dev**. Plain HTML + CSS — no build step, no JS framework, no node_modules. Deploys directly to any static host.

## Preview locally

```bash
python -m http.server 8000 --directory website
# open http://localhost:8000
```

## Structure

```
website/
├── index.html       hero, features, comparison, install snippet, CTAs
├── styles.css       standalone styles; mirrors the rust-orange palette in ../docs/stylesheets/extra.css
├── assets/
│   └── logo.svg     copied from ../docs/assets/logo.svg
└── README.md        you are here
```

## Why a separate site?

The MkDocs Material site under [`../docs/`](../docs/) is for **technical documentation** — quickstart, config reference, design docs, guides. This site is for **marketing** — the first-touch landing page someone visiting `hooksmith.dev` for the first time should see. Splitting them keeps each surface focused and lets us iterate on marketing copy without rebuilding the docs.

Both sites share the same rust-orange color palette (`--hs-rust-*` tokens) so the brand is consistent.

## Deploy

The site is intentionally trivial to host:

- **Cloudflare Pages / Netlify / Vercel**: point at the `website/` directory, no build command, publish directory `.`.
- **GitHub Pages**: serve from `website/` on the gh-pages branch, or via a workflow that copies `website/*` into the deploy artifact.
- **S3 / Cloudfront**: `aws s3 sync website/ s3://hooksmith.dev/`.

The docs at `hooksmith.dev/docs/` (or `docs.hooksmith.dev`) are deployed separately by `mkdocs` per the release process in [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## When to add a build step

Stay on plain HTML until one of these becomes painful:

- More than three or four pages with shared layout (consider [Astro](https://astro.build/) or [11ty](https://www.11ty.dev/)).
- A blog or changelog page that needs MDX/markdown.
- Live interactive demos (then a real React/Vue app under a separate directory).

Until then: open `index.html` in a text editor, make the change, refresh the browser. That's the whole loop.
