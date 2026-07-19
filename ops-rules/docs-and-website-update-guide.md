# Docs & Website Update Guide (openclaw-mem)

> **Read this before touching README.md, docs/, overrides/, or mkdocs.yml.**
> Purpose: any agent or human can update content while keeping the same design
> language, voice, and claim discipline. This file is maintainer-facing and is
> not published to the site (`ops-rules/` sits outside `docs_dir`).

---

## 0. TL;DR checklist for any docs/site change

1. Find where the claim lives (§1 surface map) — change it in its **single source** first.
2. Follow the design system (§2) — reuse `.ocm-*` components, never invent ad-hoc styles.
3. Follow the voice rules (§3) — every number needs a receipt; no invented praise.
4. Use the matching recipe (§4).
5. Verify (§5): `uv run mkdocs build --strict` **must** pass; preview both color schemes.
6. Commit `docs: <what>` → push to `main` → GitHub Pages deploys automatically (`.github/workflows/pages.yml`).

## 1. Surface map — where each kind of content lives

| Surface | File(s) | Role | Notes |
| --- | --- | --- | --- |
| **Product landing** (site home) | `overrides/home.html` + product section of `docs/stylesheets/landing.css` | Marketing/conversion page | Rendered only by `docs/index.md` via `template: home.html`. Full-bleed sections, raw HTML. |
| `docs/index.md` | front-matter only | Binds the template | Body stays empty. Do not put content here. |
| **README.md** | repo root | GitHub-facing product page | Mirrors landing claims in markdown; FAQ + harness probes live here in `<details>`. |
| **Docs pages** | `docs/*.md` | Usage/reference | Ordinary Material markdown. May use `.ocm-card`/`.ocm-grid`/`.ocm-kicker` sparingly. |
| **zh edition** | `docs/zh/index.md` | Separately written zh-Hant edition | Keeps the markdown-based hero (`.ocm-hero`). English is canonical; zh is not a line-by-line translation. |
| **Theme & nav** | `mkdocs.yml` | Tabs, palette, extensions | 7 top-level tabs (Home / Start here / Showcase / Reference / Advanced Labs / Archive / 繁體中文). Keep it at 7. |
| **Design system** | `docs/stylesheets/landing.css` | All `.ocm-*` components + Material palette hooks | Two zones: shared components (top) and product-landing zone (bottom, `.ocm-home` scope). |
| **Maintainer archive** | `exclude_docs` block in `mkdocs.yml` | Keeps specs/receipts out of the public site | If you add maintainer-only md under `docs/`, extend `exclude_docs`. |

### 1.1 Claim → single source of truth

| Claim | Source of truth | Also displayed at |
| --- | --- | --- |
| Version, release highlights, SLO table, gate metrics | `docs/releases-v<X>.md` | landing stats strip + "Numbers with receipts"; README quick links |
| Positioning tagline ("memory layer you can audit", "governance not recall") | README opening + landing hero | keep word-for-word aligned |
| Comparison table rows | README "How it compares" | landing comparison (trimmed copy) |
| Install commands / extras | README "See it in 30 seconds" | landing hero + quickstart section |
| Shipped-vs-lab status | `docs/reality-check.md` | never contradict it anywhere |

**Rule: update the source first, then its mirrors, in the same commit.**

## 2. Design system

### 2.1 Brand tokens (defined at top of `landing.css`)

| Token | Value | Meaning / use |
| --- | --- | --- |
| `--ocm-ink` | `#0b1220` | Base dark: header, hero, final CTA backgrounds |
| `--ocm-accent` / `--ocm-accent-strong` | `#10b981` / `#059669` | Emerald = "verified/governed". Primary buttons, kickers, top borders, links |
| `--ocm-amber` | `#f59e0b` | Receipts/attention accents (tile borders) — sparingly |
| `--ocm-cyan` | `#22d3ee` | Secondary accent (tile borders, glow) — sparingly |
| radius | 18px hero/banner, 14px cards, 10px buttons/inputs | never square, never pill (except `.ocm-pills`) |
| fonts | Inter (text), JetBrains Mono (code) | set in `mkdocs.yml theme.font` |

Both color schemes are mandatory: light (`default`) and dark (`slate`). Any new
component needs a `[data-md-color-scheme="slate"]` check if it uses non-token colors.

### 2.2 Component inventory (`.ocm-*`)

Shared (usable in any docs page via `attr_list`/`md_in_html`):

- `.ocm-hero` — card-style hero (used by zh landing)
- `.ocm-eyebrow` / `.ocm-kicker` — section labels (dark bg / content area)
- `.ocm-pills` — chip row
- `.ocm-terminal` — terminal window with traffic lights (title via `::before`; override per-context like `.ocm-qs-term`)
- `.ocm-grid` + `.ocm-card` (+ `.ocm-ico`, `.ocm-step`) — card grids
- `.ocm-stats` + `.ocm-stat` — trinity stat tiles
- `.ocm-banner` — CTA banner
- `.md-button` / `.md-button--primary` — buttons (primary = emerald gradient)

Product landing only (scoped `.ocm-home`, template file only):

- `.ocm-hp` (section) / `.ocm-alt` (alternating bg) / `.ocm-wrap` (61rem container)
- `.ocm-hp-hero`, `.ocm-hp-strip` + `.ocm-tile`, `.ocm-steps`, `.ocm-proof`,
  `.ocm-slo`, `.ocm-compare`, `.ocm-qs`, `.ocm-faq`, `.ocm-hp-final`
- `.ocm-install` + `.ocm-copy` (clipboard one-liner)

**Rule: compose from these first. New component ⇒ add to `landing.css` with
tokens + dark-scheme handling + a one-line entry in this inventory.**

### 2.3 Landing page section order (do not reshuffle casually)

`hero → receipt strip → problem → how-it-works → proof → features → numbers → comparison → quickstart → FAQ → final CTA`

The narrative is: hook → credibility → pain → mechanism → evidence → capability
→ performance → positioning → action → objections → action. If you add a
section, place it so the narrative still reads in that arc, and alternate
`.ocm-alt` backgrounds.

## 3. Content & voice rules

1. **Receipts culture**: every quantitative claim (latency, test count, MRR,
   version) must trace to a committed artifact — release notes, CI, or an SLO
   receipt in-repo. If you can't link it, don't claim it.
2. **No fabricated social proof**: no invented testimonials, user counts, logos
   of companies that didn't consent. "Social proof" here = reproducible proof
   outputs and real receipts.
3. **Honest positioning**: we do not claim to beat recall-focused products at
   recall. The comparison table stays two-sided and respectful. Never remove
   the "honest framing" sentence.
4. **Reality-check supremacy**: nothing on the landing/README may contradict
   `docs/reality-check.md`. Labs stay labeled labs.
5. **Language**: site + README canonical in English. zh-Hant edition is a
   separately written page (not machine-mirrored); update it when meaning
   changes, not for every wording tweak. 中文術語跟隨 zh page 既有選字。
6. **Precision vocabulary**: sidecar / memory slot / receipt / ContextPack /
   quarantined / fail-open are defined terms — use them exactly as defined in
   README "Words we mean precisely" (zh page mirrors definitions).
7. Tone: confident, concrete, zero hype-adjectives ("revolutionary",
   "blazingly" are banned). Verbs over adjectives; evidence over emphasis.

## 4. Update recipes

### 4.1 Release day (new version vX.Y.Z)

1. Write `docs/releases-vX.Y.Z.md` (highlights, upgrade posture, SLO table,
   verification) — this is the claim source.
2. Landing `overrides/home.html`:
   - stats strip: the four `data-stat` tiles (`version`, `tests`, `slo`,
     `quality`) — update numbers + captions.
   - "Numbers with receipts" SLO table rows.
   - link target `releases-vX.Y.Z/`.
3. README: version-dependent lines + quick-links row.
4. `mkdocs.yml`: nav entry "What's new in vX.Y.Z"; adjust `exclude_docs`
   negation (`!releases-vX.Y.Z.md`) if the old-releases exclusion pattern
   would swallow it.
5. zh page: update only if the product story changed.
6. Verify (§5), single commit `docs: refresh site for vX.Y.Z`, push.

### 4.2 Add a docs page

1. Create `docs/<name>.md` (kebab-case). One `#` H1; use `.ocm-kicker` +
   admonitions for structure; keep code fences copy-runnable.
2. Add to `mkdocs.yml` nav under the right tab: user-journey pages → *Start
   here*; proofs/demos → *Showcase*; contracts/ops → *Reference*; opt-in lanes
   → *Advanced Labs*. Do not create new top-level tabs.
3. If maintainer-only: add to `exclude_docs` instead of nav.

### 4.3 Edit a landing section

1. Locate the section by its HTML comment banner in `overrides/home.html`.
2. Edit copy in place; reuse component classes; keep links root-relative
   (`quickstart/` style — the template renders only at site root).
3. Keep the hero h1 ≤ 8 words and the sub ≤ 3 sentences.
4. Verify §5 including mobile width (≤ 44rem) and both schemes.

### 4.4 Add a harness quickstart

`docs/quickstart-<harness>.md` + nav under *Start here → Harness quickstarts* +
add the link to the landing quickstart side list + README if the harness list
is enumerated there.

### 4.5 Touch the zh edition

Only `docs/zh/index.md` exists today. It keeps the markdown `.ocm-hero` layout
(not the home template). If you port the landing to zh later, create
`overrides/home-zh.html` following the same section order and bind it from the
zh page front-matter.

## 5. Verification protocol (before every push)

```bash
uv sync --locked --extra docs
uv run mkdocs build --strict        # the exact CI gate — must pass with zero warnings
uv run mkdocs serve -a 127.0.0.1:8137   # manual preview
```

Check: landing renders (hero, strip, tables), palette toggle both ways, one
docs page (e.g. quickstart) still normal, tabs intact, README preview on
GitHub after push. Never commit `site/` (gitignored) or lockfile changes you
didn't intend (`uv lock --check` runs in CI).

## 6. Hard do-nots

- ❌ No external JS/CSS/CDNs. The only allowed runtime script is the tiny
  inline clipboard handler in `home.html`. (Fonts come via Material's built-in
  Google Fonts config only.)
- ❌ Don't rename `.ocm-*` classes without grepping `docs/**/*.md` (zh page
  uses them) and this guide.
- ❌ Don't put content into `docs/index.md` — it's a template binder.
- ❌ Don't add an 8th top-level tab; regroup instead.
- ❌ Don't weaken `exclude_docs`; specs/receipts/blade-maps stay out of the
  public site.
- ❌ Don't state unshipped features as shipped (roadmap/labs language exists
  for that), and don't edit generated `site/`.
- ❌ Don't change `site_url` / `repo_url` / entry-point names.

## 7. File map

```text
overrides/home.html                     product landing (Jinja template, HTML sections)
docs/index.md                           front-matter binder → home.html
docs/stylesheets/landing.css            design system: shared components + .ocm-home zone
docs/assets/favicon.svg                 brand mark (ink square + emerald check on db)
mkdocs.yml                              theme (custom_dir: overrides), tabs, extensions, exclude_docs
README.md                               GitHub product page (markdown mirror of landing claims)
docs/zh/index.md                        zh-Hant edition (markdown hero)
.github/workflows/pages.yml             push to main → strict build → Pages deploy
ops-rules/docs-and-website-update-guide.md   this guide
```
