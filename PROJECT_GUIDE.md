# mdchunk — Project Specification and Development Guide

## 1. Project objective

Build a lightweight Python library that converts structured English Markdown documents into
high-quality chunks suitable for downstream RAG pipelines.

The library should focus exclusively on:

- Markdown parsing
- document structure
- semantic chunk boundaries
- chunk sizing
- controlled overlap
- source metadata

It should not perform embeddings, retrieval, reranking, generation, vector database operations,
or LLM-based semantic analysis.

---

## 2. Core design principles

### 2.1 Structure before size

The algorithm should prefer:

1. document boundaries
2. headings
3. semantic block boundaries
4. paragraph/sentence boundaries
5. size limits
6. hard character/word splitting only as a final fallback

A chunk should never be split merely because a character counter reached a threshold if a better
semantic boundary is available nearby.

### 2.2 Preserve hierarchy

For:

```markdown
# Authentication
## Login
### Password reset
```

the heading path should be represented as:

```text
Authentication
Authentication > Login
Authentication > Login > Password reset
```

The hierarchy is metadata first. A readable breadcrumb can optionally be included in chunk text.

### 2.3 Do not invent headings

Ordinary prose must not be promoted to a heading merely because it:

- is uppercase
- starts with "Chapter"
- starts with a number
- looks like a title
- appears on a short line

Only actual Markdown headings should define hierarchy.

This avoids corrupting the heading stack from a false positive.

---

## 3. Dependencies

The core dependency should remain minimal.

### Required

- `markdown-it-py`

### Not required by core

- transformers
- torch
- sentence-transformers
- LangChain
- LlamaIndex
- OpenAI SDKs
- vector database clients

### Optional future functionality

Tokenizer-specific sizing may be provided through an adapter or optional extra.

For example:

```text
core
  CharacterSizeMetric

optional integration
  TokenizerSizeMetric
```

This prevents a lightweight library from forcing a large ML dependency tree onto every user.

---

## 4. Public API

Keep the public API small and stable.

Recommended:

```python
from mdchunk import (
    chunk_markdown,
    MarkdownChunker,
    ChunkerConfig,
    Chunk,
    ChunkMetadata,
)
```

Example:

```python
chunks = chunk_markdown(markdown)
```

Advanced users can instantiate:

```python
chunker = MarkdownChunker(config)
chunks = chunker.chunk(markdown)
```

Internal implementation details should not be part of the public contract.

---

## 5. Chunk model

A chunk should contain:

```text
text
metadata
```

Metadata should support at least:

- chunk ID
- chunk index
- chunk type
- heading path
- start line
- end line
- start offset
- end offset
- measured size
- size metric

This allows downstream systems to attach document IDs, URLs, filenames, permissions, page
references, or other application-specific information without coupling the library to a database.

---

## 6. Supported semantic blocks

The initial implementation should explicitly understand:

### Headings

- H1
- H2
- H3
- deeper headings

### Paragraphs

Normal prose should be split at sentence boundaries when needed.

### Lists

Lists should remain intact where possible.

A large list may eventually need specialized item-level splitting.

### Tables

Tables should be treated as structured data.

If a table is too large:

- retain the table header
- split between rows
- never split in the middle of a row

### Code blocks

Fenced and indented code blocks should be preserved as atomic blocks whenever they fit.

Very large code blocks may be hard-split only as a last resort.

### Blockquotes

Preserve blockquotes as coherent blocks when possible.

---

## 7. Sentence splitting

The library should not depend on an NLP model merely to split English sentences.

A conservative deterministic splitter is sufficient for the initial implementation.

It should avoid common false boundaries involving:

- decimal numbers
- common abbreviations
- initials
- URLs where practical

Sentence splitting should be treated as a fallback for oversized prose, not as the primary
representation of document structure.

Future versions may expose a pluggable sentence splitter if there is demonstrated demand.

---

## 8. Chunk size strategy

Use a target and maximum rather than a single threshold.

Example:

```text
target_size = 700
max_size    = 1000
```

Conceptually:

```text
small content
     |
     v
accumulate semantically
     |
     v
target reached
     |
     v
look for a natural boundary
     |
     v
never exceed max unless an atomic block
must be handled specially
```

The exact defaults should be benchmarked rather than treated as universal truths.

Different embedding models and document types may benefit from different budgets.

---

## 9. Size metrics

Character count should be the default because it is:

- fast
- deterministic
- dependency-free
- model-independent

The architecture should allow:

- character count
- word count
- custom callable
- optional tokenizer count

Do not install a large tokenizer stack merely to provide token-aware chunking to users who
do not need it.

---

## 10. Overlap strategy

Overlap should improve continuity without destroying semantic boundaries.

Recommended behavior:

- use trailing sentences
- apply overlap mainly within the same heading path
- do not blindly overlap across major sections
- ensure overlap does not push the new chunk beyond the configured maximum

Overlap should be configurable and may be disabled with:

```python
ChunkerConfig(overlap=0)
```

---

## 11. Tables

Tables deserve special attention because RAG retrieval can become misleading if table context
is lost.

Example:

```markdown
| Product | Limit |
|---|---:|
| A | 100 |
| B | 200 |
| C | 500 |
```

If this must be split, each resulting chunk should retain:

```markdown
| Product | Limit |
|---|---:|
```

before its subset of rows.

Future improvements could add:

- row-group awareness
- repeated contextual headings
- configurable table serialization
- optional conversion to natural-language row representations

These should be added only after benchmark evidence shows value.

---

## 12. Metadata and source tracking

Line numbers and offsets should be preserved whenever the parser provides them.

Recommended future metadata fields:

- source document ID
- filename
- URL
- page number
- section title
- document title
- language
- checksum/version

Application-specific metadata should be attached by the caller rather than hard-coded into
the core library.

---

## 13. Error handling

The library should:

- validate configuration early
- raise clear `TypeError`/`ValueError` messages for invalid API usage
- return an empty list for empty Markdown
- avoid crashing on ordinary malformed Markdown where the parser can recover

Do not silently hide programming errors.

---

## 14. Performance

Performance matters because chunking can run over large document collections.

Important practices:

- instantiate the Markdown parser once per `MarkdownChunker`
- avoid repeated full-document regex processing
- avoid unnecessary copying of large strings
- use linear passes where possible
- avoid quadratic list/string operations
- avoid loading ML models
- avoid network calls
- benchmark both throughput and memory

For very large documents, consider a streaming/block-oriented API in a later version.

---

## 15. Testing strategy

Unit tests should cover:

### Basic

- empty Markdown
- one paragraph
- multiple paragraphs
- one heading
- nested headings
- missing heading levels
- deep heading levels

### Chunk boundaries

- below target
- target reached
- maximum reached
- oversized sentence
- oversized paragraph
- multiple sections
- overlap enabled
- overlap disabled
- overlap across section boundaries

### Tables

- small table
- large table
- table header preservation
- multiline cells if supported
- malformed tables

### Code

- Python code
- JSON
- SQL
- long code block
- fenced code without language
- indented code

### Lists

- unordered
- ordered
- nested lists
- long lists

### Other Markdown

- links
- images
- emphasis
- inline code
- blockquotes
- HTML
- escaped characters
- Unicode

### Robustness

- malformed Markdown
- extremely long lines
- documents with no headings
- documents with many headings
- very small max size
- very large max size

---

## 16. Regression corpus

Unit tests alone are not enough.

Create a real Markdown corpus containing representative:

- technical documentation
- policies
- manuals
- API documentation
- reports
- FAQs
- knowledge-base articles
- tables
- procedures

Every discovered bug should become a regression test.

The goal is to ensure future algorithm improvements do not silently reintroduce previous failures.

---

## 17. Retrieval benchmark

The most important long-term validation is downstream retrieval quality.

Create a benchmark containing:

```text
documents
questions
ground-truth source sections/chunks
```

Compare your chunker against baselines such as:

- fixed character splitting
- fixed word splitting
- recursive splitting
- simple Markdown heading splitting

Keep constant:

- documents
- questions
- embedding model
- vector store
- similarity metric
- top-k
- retrieval configuration

Change only the chunking strategy.

Measure at least:

- Recall@k
- Precision@k where appropriate
- MRR
- nDCG where appropriate
- chunk count
- average chunk size
- size distribution

This gives evidence for whether the chunking strategy actually improves RAG retrieval.

---

## 18. Do not claim "perfect chunks"

Avoid marketing claims such as:

> Perfect RAG chunks.

Prefer:

> Structure-aware Markdown chunking optimized for retrieval-augmented generation.

Once a benchmark exists, stronger claims can be made only when supported by reproducible results.

---

## 19. Package structure

Recommended:

```text
mdchunk/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── src/
│   └── mdchunk/
│       ├── __init__.py
│       ├── chunker.py
│       ├── models.py
│       ├── metrics.py
│       └── ...
├── tests/
├── examples/
├── benchmarks/
└── .github/
    └── workflows/
```

Use a `src/` layout to prevent accidental imports from the repository root.

---

## 20. CI/CD

GitHub Actions should eventually run:

```text
push / pull request
       |
       +--> tests
       +--> coverage
       +--> lint
       +--> type checking
       +--> package build
```

Test supported Python versions explicitly.

A sensible initial matrix is the minimum supported version plus current stable versions.

---

## 21. Versioning

Use semantic versioning.

During algorithm/API experimentation:

```text
0.x.y
```

is appropriate.

After the public API is stable:

```text
1.0.0
```

Use:

- PATCH for bug fixes
- MINOR for backwards-compatible features
- MAJOR for breaking changes

Because chunking behavior itself affects downstream systems, document meaningful algorithm changes
even when the Python API remains compatible.

---

## 22. Framework integrations

Keep integrations outside the core.

Core:

```python
from mdchunk import chunk_markdown
```

Potential optional integrations later:

```text
mdchunk[langchain]
mdchunk[llamaindex]
mdchunk[haystack]
```

The core package should never require these frameworks.

---

## 23. Documentation

The README should answer these questions quickly:

1. What is it?
2. Why is Markdown-aware chunking useful?
3. How is it different from naive splitting?
4. How do I install it?
5. How do I use it?
6. What does a Chunk contain?
7. How do I configure size/overlap?
8. How do I provide a custom size metric?
9. What Markdown structures are preserved?
10. What are the limitations?

Later add:

- API reference
- architecture documentation
- benchmark results
- examples
- migration guides
- changelog

---

## 24. Development roadmap

### Phase 1 — Core

- Markdown parser
- block extraction
- heading hierarchy
- semantic chunking
- size metrics
- Chunk model
- metadata
- tables
- code
- lists
- overlap

### Phase 2 — Quality

- large regression corpus
- performance benchmarks
- edge-case tests
- memory profiling
- retrieval benchmark

### Phase 3 — Public release

- README
- API documentation
- license
- CI
- package build
- PyPI
- GitHub release

### Phase 4 — Extensions

Only after the core is stable:

- tokenizer metric
- streaming API
- richer table strategies
- optional integrations
- configurable sentence splitters
- additional language support

---

## 25. Things to avoid

Do not:

- make Transformers a core dependency
- require an LLM for chunking
- couple the package to a vector database
- couple it to one embedding model
- infer headings aggressively from plain text
- split every block purely by characters
- claim universal optimal chunk sizes
- add dozens of dependencies before they are necessary
- expose internal classes as the public API prematurely
- optimize microseconds before measuring real workloads

---

## 26. Important architectural principle

The library should solve exactly one problem well:

> Convert structured Markdown into coherent, size-controlled, metadata-rich chunks.

Everything after that belongs to the application.

```text
Markdown
   ↓
mdchunk
   ↓
Chunk objects
   ↓
embedding model
   ↓
vector database
   ↓
retrieval
   ↓
LLM
```

This separation is what makes the library broadly reusable.

---

## 27. Recommended first public release

The first release should be deliberately small.

Target:

```text
mdchunk 0.1.0
```

with:

- one stable convenience function
- one main Chunker class
- typed Chunk and metadata models
- Markdown parsing
- heading hierarchy
- paragraphs
- lists
- code
- tables
- blockquotes
- configurable size
- configurable overlap
- source locations
- no ML dependencies
- strong tests

Do not try to solve every possible Markdown/RAG problem in 0.1.0.

---

## 28. Long-term differentiator

The strongest differentiator should not be:

> "We have another Markdown splitter."

It should eventually be:

> "We have a reproducible, empirically evaluated strategy for converting structured Markdown into retrieval-effective chunks."

That means the benchmark and evaluation methodology can become as important as the implementation.

A high-quality package plus a reproducible benchmark is considerably more compelling than a large codebase with no evidence that its chunks improve retrieval.
