# mdchunker

Lightweight, structure-aware Markdown chunking for retrieval-augmented generation (RAG).

## Goals

- Preserve Markdown hierarchy.
- Keep semantic blocks together where practical.
- Handle paragraphs, headings, tables, lists, code blocks, and blockquotes.
- Split oversized prose at sentence boundaries before falling back to hard splits.
- Preserve table headers when large tables must be split.
- Attach useful source metadata.
- Remain independent of LLMs, embedding models, vector databases, and RAG frameworks.
- Keep the core dependency footprint small.

## Installation

```bash
pip install mdchunker
```

## Basic usage

```python
from mdchunker import chunk_markdown

chunks = chunk_markdown(markdown)

for chunk in chunks:
    print(chunk.text)
    print(chunk.metadata.heading_path)
```

## Size control

The default metric is characters so the core package does not need a tokenizer.

```python
from mdchunker import ChunkerConfig, chunk_markdown

config = ChunkerConfig(
    target_size=700,
    max_size=1000,
    overlap=100,
)

chunks = chunk_markdown(markdown, config=config)
```

A custom size metric can be supplied later for tokenizer-specific budgets without making
a tokenizer a core dependency.

## Design philosophy

The library is a preprocessing component:

Markdown -> structural parsing -> semantic chunking -> Chunk objects

Embedding, reranking, retrieval, vector storage, and generation remain outside the library.

## Important limitations

The first release intentionally avoids trying to infer headings from ordinary prose.
Markdown structure is trusted rather than guessed. Malformed Markdown is parsed using
CommonMark-compatible behavior, but no parser can perfectly recover missing structure.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src
python -m build
```
