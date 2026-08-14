# Changelog

## Unreleased — pre-0.1.0 correctness & robustness pass

### Renamed: markdown-chunker → mdchunk

The PyPI name `markdown-chunker` is already taken by an actively published,
purpose-similar package (structure-aware Markdown chunking with table/code
preservation), first released Feb 2025 -- confirmed live on PyPI, not just
reserved. Renamed the distribution name, the importable package
(`src/markdown_chunker/` → `src/mdchunk/`), and every reference across the
codebase and docs to `mdchunk` before this was ever published, so PyPI name
and import name match exactly (`pip install mdchunk` / `import mdchunk`).
No behavior changed; this is a pure rename, verified with a full clean
reinstall and the entire test/lint/type/build suite passing afterward.

This pass was triggered by actually running the original test suite (3 of 4
tests failed immediately) and then stress-testing the chunker against inputs
outside the original test file: real tables, nested lists, blockquotes,
HTML, oversized content, and larger documents. Every issue below was
reproduced with a minimal example before being fixed, and every fix has a
regression test in `tests/test_basic.py`.

No dependencies were added. `markdown-it-py` remains the only core
dependency. The default size metric remains character-based
(`CharacterSizeMetric`); no tokenizer or LLM is used anywhere in the core
path.

### Fixed — crashes / silent data loss

- **Sentence splitter crashed on any prose long enough to need splitting.**
  The abbreviation-protection regex used a negative lookbehind with
  alternatives of different lengths (`Mr`, `Mrs`, `Prof`, ...), which
  Python's `re` module cannot compile (`re.error: look-behind requires
  fixed-width pattern`). This broke 3 of the original 4 tests. Rewritten as
  a chain of individual fixed-width lookbehinds. The original logic also
  checked the wrong string position (after the terminal punctuation instead
  of including it), so a syntactically-valid version would still never have
  actually protected "Mr." from a false split.

- **Tables were never actually parsed as tables.** `MarkdownIt("commonmark",
  ...)` does not include GFM tables (they are not part of vanilla
  CommonMark), so no `table_open` token was ever emitted. Every table in
  every document was silently parsed as one ordinary paragraph and then
  mangled by the prose splitter (pipes and rows flattened onto one
  space-joined line). Fixed with `.enable("table")` — the rule already
  ships inside `markdown-it-py`, so this required no new dependency.

- **Raw HTML blocks were silently dropped** — not preserved, not
  hard-split, just missing from the output entirely. Added `html_block`
  token handling and a new `CHUNK_HTML` ("html") chunk type, plus a
  `preserve_html_blocks` config flag for consistency with the other
  `preserve_*` options.

- **List markers, ordering, and nesting were destroyed for every list**,
  not just oversized ones. `"1. First step"` became bare `"First step"`,
  and nested sub-items were flattened to the same level as their parent
  with no indication of the relationship. Replaced the plain-text extractor
  with a recursive renderer (`_render_list_items` / `_render_list_item`)
  that reconstructs bullet/number markers, respects a custom ordered-list
  `start` number, and indents nested sub-lists two spaces per level.

- **Blockquote `>` markers were destroyed** the same way, including for
  nested blockquotes. Replaced with a recursive `_render_blockquote` that
  preserves nesting (each level adds one more `>`).

- **Blockquotes silently dropped any nested code block, list, or table.**
  `_render_blockquote` originally only handled plain paragraphs and nested
  blockquotes — a fenced code block, list, or table inside a blockquote
  (all legal CommonMark) fell through unhandled and was discarded, the same
  class of bug as the HTML-block issue above, just one level deeper.
  Rewritten to handle every block type a blockquote can legally contain,
  reusing the same renderers used for top-level content.

- **Multi-paragraph ("loose") list items lost their paragraph breaks.**
  `1. First step` followed by a second paragraph under the same item was
  joined onto the first with a single space, indistinguishable from one
  long paragraph. Fixed: the first paragraph sits on the marker's line,
  and any further paragraphs are blank-line-separated and indented to
  align under it, matching CommonMark's own continuation-paragraph
  convention.

- **`chunk_type` priority order for mixed structured content was
  arbitrary and unpredictable.** An earlier fix used a fixed priority
  order (table > code > list > blockquote > html) whenever a chunk
  contained more than one structured kind, which a reader would have no
  way to predict. Replaced with: plain prose never outranks any
  structured kind regardless of size (fixes the original bug and the
  short-code-snippet case), but when two or more *different* structured
  kinds genuinely coexist in one chunk, the one that actually contributes
  more content decides — real signal instead of a silent fixed order.

### Fixed — wrong output / misleading metadata

- **`chunk_type` frequently reported `"text"` for chunks that were actually
  a table, code block, or list.** The original classifier only returned a
  specific type when a chunk consisted *purely* of that one kind, but
  headings routinely get merged into the same chunk as the content beneath
  them (correct, size-driven behavior) — so the kind-set was almost never a
  clean singleton. Replaced with presence-based priority classification
  (table > code > list > blockquote > html > text): if a chunk contains any
  block of a given kind, it is labeled accordingly, regardless of how many
  characters of surrounding prose happen to be attached. (An earlier
  size-dominant version was tried first but also mislabeled short-but
  -significant blocks, e.g. a one-line code snippet next to a slightly
  longer intro sentence — fixed by moving to presence, not size.)

- **`preserve_tables`, `preserve_code_blocks`, `preserve_lists`, and
  `preserve_blockquotes` were silent no-ops.** Each was computed and stored
  on the corresponding `_Block.splittable` field but never once read
  anywhere in the chunking algorithm — confirmed by diffing output with the
  flag on vs. off on oversized content (byte-identical). Also fixed an
  inverted-boolean bug in the process (the raw config value was being
  stored where its negation was needed). These flags now genuinely control
  whether oversized content of that kind is kept atomic (with
  kind-specific splitting, e.g. table-header repetition) or falls back to
  generic prose-style splitting.

- **Table column alignment (`:---`, `---:`, `:---:`) was discarded** and
  replaced with a generic `---` on every reconstructed table, including
  ones that were never even split. Now read from the header cells'
  `text-align` style and preserved in the rebuilt separator row.

- **Overlap could duplicate an entire heading label.** When a chunk's whole
  content was just a heading line with no body yet (e.g. a heading
  immediately followed by an oversized table that got pushed into its own
  chunk), the overlap step glued that *entire* heading-only chunk onto the
  next chunk as "continuity" — even though the next chunk already carried
  the same heading as its own breadcrumb prefix, producing text like
  `"Limits\n\nLimits\n\n<table>"`. Fixed by computing the overlap tail from
  each chunk's own body content only, never from its heading-path prefix;
  if a chunk's entire content *is* its heading prefix, no overlap tail is
  taken from it.

### Fixed — quality / robustness

- **Oversized lists were hard-split at arbitrary character offsets**,
  cutting items in half mid-word (`"...descriptive detail about the item\n
  item number 4..."`, with the tail of item 3 orphaned into the next
  chunk). Added `_split_list`, which groups whole top-level items
  (including their nested sub-items) up to `max_size`, only falling back to
  a character-level split for the rare single item that alone exceeds
  `max_size`.

- **Sentence splitting mishandled initials** ("J. R. R. Tolkien" was
  shredded into four fragments) — explicitly called out as a required case
  in `PROJECT_GUIDE.md` §7 but not actually handled. Added a lookbehind
  that protects a single capital letter followed by a period. Also added
  a few very common abbreviations (`a.m.`, `p.m.`, `cf.`, `al.`) to the
  existing list.

- **Dead code removed**: a no-op loop in the original table-reconstruction
  helper (`tokens.index(token) if False else -1`, executed once per token
  for no effect) and the now-unused marker-stripping `_tokens_plain_text`
  helper it was part of.

### Performance

- **Offset tracking was O(document size × block count) instead of
  O(document size).** `_offset`/`_end_offset` each re-ran `source.
  splitlines(keepends=True)` over the *entire* document and re-summed line
  lengths from scratch, once per block, for both the start and end offset
  of every single block. Profiling a ~150K-character synthetic document
  showed this accounted for ~90% of total runtime. Fixed by computing a
  line-offset table once per document (`_line_offsets`) and doing an O(1)
  lookup per block afterward.
  - Measured effect on the same document: **2.3s → 0.2s (≈11.6x)**.
  - Scaling changed from clearly super-linear to roughly linear across
    150–1600-section synthetic documents (doubling the document now
    roughly doubles the time, not quadruples it). A regression test
    (`test_chunking_time_scales_roughly_linearly`) guards against this
    being reintroduced.

### Type checking / lint

- Fixed all `mypy --strict` findings introduced or exposed by the above
  changes (an untyped callable parameter, a dynamically-set class attribute
  that mypy couldn't type — replaced with `functools.lru_cache` on a
  module-level function — and a couple of `token.attrs` values that needed
  an explicit `str`/`int` coercion since markdown-it-py types attribute
  values as a broad union).
- Fixed import ordering (`ruff --select I001`) in the two source files and
  the test file. Did **not** apply `ruff`'s `X | None` modernization
  suggestions (`UP006`/`UP045`): this project targets Python 3.9+, and
  `models.py` does not use `from __future__ import annotations`, so that
  syntax would break on 3.9.

- **A blockquote directly nested inside a list item lost its `>` marker
  and silently dropped a fenced code block inside that blockquote.** Found
  by the new regression corpus (`tests/corpus/messy_edge_cases.md`), not by
  hand-written unit tests -- exactly the kind of bug a corpus is for.
  `_render_list_item` only recognized plain paragraphs and nested sub-lists;
  a directly-nested blockquote fell through to the unhandled branch, which
  let the blockquote's own inner paragraph token leak into the item's
  top-level scan (losing its `>` prefix) and dropped anything after it
  (here, a fenced code block) entirely. Generalized to handle every block
  type a list item can directly contain (blockquote, code, table, HTML),
  matching the same fix already made for blockquotes-containing-other-things
  earlier in this pass.

### Added

- `CHUNK_HTML` chunk type and `preserve_html_blocks` config option.
- 54 regression tests total (up from 4): 29 in `tests/test_basic.py` (one
  per bug above) plus a new `tests/test_corpus.py` with 25 invariant-based
  tests run against a small regression corpus (`tests/corpus/*.md`) of
  realistic documents (API reference, policy/FAQ, and a deliberately messy
  edge-case document), per `PROJECT_GUIDE.md` section 16. Extend the corpus
  by dropping more `.md` files into `tests/corpus/` -- most of the tests
  pick them up automatically.
- Repo infrastructure for pushing to GitHub: `.gitignore`, `LICENSE` (MIT,
  matching `pyproject.toml` -- replace the `[Your Name]` placeholder before
  publishing), and `.github/workflows/ci.yml` (lint + type-check + test
  with coverage + a packaging build check, across a Python 3.9/3.11/3.12/
  3.13 matrix, on every push and pull request).
- An explicit `[tool.ruff.lint] select` in `pyproject.toml`. Previously
  unset, which meant a bare `ruff check .` picked up ruff's broader
  defaults and flagged ~80 pre-existing type hints (`Optional[X]`,
  `List[X]`) as "modernize to `X | None"/"list[X]`" -- suggestions that
  would actually break the declared Python 3.9 support if applied, since
  `models.py` and `metrics.py` don't use
  `from __future__ import annotations`. Selected a correctness-focused set
  instead (`E`, `F`, `I`, `B`, `RUF`); see the comment in `pyproject.toml`
  for the reasoning and how to revisit it later.

### Known remaining limitations (not fixed in this pass — flagged, not silently left broken)

- A genuine sentence that happens to end in a single capital letter (rare,
  e.g. "The answer is B. That is correct.") will not be split there, since
  the same pattern that protects initials also protects this case. This is
  the intended conservative trade-off, not an oversight: the alternative is
  false-splitting every initial ("J. R. R. Tolkien"), which is far more
  common and more damaging to retrieval quality than under-splitting a rare
  single-letter sentence ending.
- The larger items from the original roadmap — a real regression corpus,
  the retrieval benchmark, and a full API review before 1.0 — are
  unchanged and still ahead of you, as originally planned.
