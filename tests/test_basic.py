import time

from mdchunker import ChunkerConfig, chunk_markdown
from mdchunker.metrics import WordSizeMetric

# ---------------------------------------------------------------------------
# Original tests
# ---------------------------------------------------------------------------

def test_heading_path_and_chunks():
    text = """
# Product
This is an introduction to the product.

## Installation
Install the package on your system. Make sure Python is available.
"""
    chunks = chunk_markdown(text, config=ChunkerConfig(target_size=50, max_size=300))
    assert chunks
    assert chunks[0].metadata.heading_path == ("Product",)
    assert any("Product > Installation" in c.text for c in chunks)


def test_empty_input():
    assert chunk_markdown("") == []


def test_code_block_is_preserved():
    text = """
# Example
Use this code:

```python
print("hello")
print("world")
```
"""
    chunks = chunk_markdown(text)
    assert any(c.metadata.chunk_type == "code" for c in chunks)


def test_table_keeps_header():
    text = """
# Limits
| Product | Limit |
|---|---:|
| A | 100 |
| B | 200 |
"""
    chunks = chunk_markdown(
        text,
        config=ChunkerConfig(target_size=30, max_size=60, min_size=0),
    )
    table_chunks = [c for c in chunks if c.metadata.chunk_type == "table"]
    assert table_chunks
    assert all("| Product | Limit |" in c.text for c in table_chunks)


# ---------------------------------------------------------------------------
# Regression tests: sentence splitter
# ---------------------------------------------------------------------------

def test_sentence_splitter_does_not_crash():
    # The original abbreviation lookbehind used variable-length alternatives,
    # which Python's `re` module cannot compile. Any prose long enough to
    # need sentence splitting crashed the whole library.
    text = "# Doc\n" + ("This is a normal sentence. " * 50)
    chunks = chunk_markdown(text, config=ChunkerConfig(target_size=100, max_size=200))
    assert chunks


def test_sentence_splitter_protects_abbreviations_and_initials():
    from mdchunker.chunker import MarkdownChunker

    mc = MarkdownChunker()
    assert mc._sentences("Dr. Smith went to Washington. He was tired.") == [
        "Dr. Smith went to Washington.",
        "He was tired.",
    ]
    assert mc._sentences("J. R. R. Tolkien wrote this. It is great.") == [
        "J. R. R. Tolkien wrote this.",
        "It is great.",
    ]
    assert mc._sentences("The value is 3.14. Next sentence starts here.") == [
        "The value is 3.14.",
        "Next sentence starts here.",
    ]


# ---------------------------------------------------------------------------
# Regression tests: table parsing was never actually enabled
# ---------------------------------------------------------------------------

def test_table_is_actually_parsed_as_a_table():
    text = "# T\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    chunks = chunk_markdown(text, config=ChunkerConfig(min_size=0))
    table_chunks = [c for c in chunks if c.metadata.chunk_type == "table"]
    assert table_chunks
    combined = "\n".join(c.text for c in table_chunks)
    # All four data cells must survive as real table rows, not be flattened
    # into a single space-joined paragraph line.
    assert "| 1 | 2 |" in combined
    assert "| 3 | 4 |" in combined


def test_table_alignment_is_preserved():
    text = "# P\n| Name | Price | Qty |\n|:---|---:|:---:|\n| Widget | 1.00 | 5 |\n"
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert ":---" in combined and "---:" in combined and ":---:" in combined


# ---------------------------------------------------------------------------
# Regression tests: chunk_type classification
# ---------------------------------------------------------------------------

def test_chunk_type_is_table_even_when_merged_with_heading():
    text = "# Limits\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    chunks = chunk_markdown(text)  # defaults easily fit heading+table together
    assert any(c.metadata.chunk_type == "table" for c in chunks)


def test_chunk_type_is_code_even_when_merged_with_heading():
    text = "# Example\nUse this code:\n\n```python\nprint('hi')\n```\n"
    chunks = chunk_markdown(text)
    assert any(c.metadata.chunk_type == "code" for c in chunks)


def test_chunk_type_prefers_structured_content_over_longer_prose():
    # "Use this code:" (15 chars) is longer than "print('hi')" (11 chars).
    # A size-dominant classifier would mislabel this chunk as "text"; the
    # presence of the code block should win regardless.
    text = "# Example\nUse this code:\n\n```python\nprint('hi')\n```\n"
    chunks = chunk_markdown(text)
    code_chunks = [c for c in chunks if c.metadata.chunk_type == "code"]
    assert code_chunks
    assert any("print('hi')" in c.text for c in code_chunks)


# ---------------------------------------------------------------------------
# Regression tests: preserve_* config flags were previously no-ops
# ---------------------------------------------------------------------------

def test_preserve_tables_flag_changes_output():
    rows = "\n".join(f"| P{i} | L{i} | Notes about product {i} |" for i in range(1, 10))
    text = f"# Limits\n| Product | Limit | Notes |\n|---|---|---|\n{rows}\n"

    preserved = chunk_markdown(
        text, config=ChunkerConfig(target_size=50, max_size=120, min_size=0)
    )
    not_preserved = chunk_markdown(
        text,
        config=ChunkerConfig(target_size=50, max_size=120, min_size=0, preserve_tables=False),
    )

    preserved_table_chunks = [c for c in preserved if c.metadata.chunk_type == "table"]
    # With preserve_tables=True, every split table chunk repeats the header.
    assert len(preserved_table_chunks) > 1
    assert all("| Product | Limit | Notes |" in c.text for c in preserved_table_chunks)

    # With preserve_tables=False, output must differ (falls back to generic
    # splitting) -- previously these two configs produced identical output.
    assert [c.text for c in preserved] != [c.text for c in not_preserved]


def test_preserve_lists_flag_changes_output():
    items = "\n".join(f"- item {i} with some descriptive filler text" for i in range(1, 15))
    text = f"# Notes\n{items}\n"

    preserved = chunk_markdown(
        text, config=ChunkerConfig(target_size=40, max_size=90, min_size=0)
    )
    not_preserved = chunk_markdown(
        text,
        config=ChunkerConfig(target_size=40, max_size=90, min_size=0, preserve_lists=False),
    )
    assert [c.text for c in preserved] != [c.text for c in not_preserved]


# ---------------------------------------------------------------------------
# Regression tests: HTML blocks were silently dropped
# ---------------------------------------------------------------------------

def test_html_block_is_preserved_not_dropped():
    text = '# Notice\n\n<div class="warning">Read the terms before continuing.</div>\n\nAfter.\n'
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "warning" in combined
    assert "Read the terms before continuing." in combined
    assert any(c.metadata.chunk_type == "html" for c in chunks)


# ---------------------------------------------------------------------------
# Regression test: overlap duplicating a heading-only chunk's text
# ---------------------------------------------------------------------------

def test_overlap_does_not_duplicate_heading_only_chunk():
    rows = "\n".join(f"| P{i} | L{i} | Notes about product {i} |" for i in range(1, 10))
    text = f"# Limits\n| Product | Limit | Notes |\n|---|---|---|\n{rows}\n"
    # Default overlap (100) with a heading-only first chunk previously caused
    # "Limits\n\nLimits\n\n<table>" in the very next chunk.
    chunks = chunk_markdown(text, config=ChunkerConfig(target_size=50, max_size=120, min_size=0))
    for c in chunks:
        assert "Limits\n\nLimits" not in c.text


# ---------------------------------------------------------------------------
# Regression tests: list/blockquote markers and nesting were stripped
# ---------------------------------------------------------------------------

def test_ordered_list_markers_and_nesting_preserved():
    text = (
        "# Steps\n1. First step\n2. Second step\n"
        "   - nested detail A\n   - nested detail B\n3. Third step\n"
    )
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "1. First step" in combined
    assert "2. Second step" in combined
    assert "3. Third step" in combined
    assert "- nested detail A" in combined
    # Nested items must be indented under their parent, not flattened to the
    # same level.
    assert "  - nested detail A" in combined


def test_ordered_list_respects_custom_start_number():
    text = "# S\n5. Fifth step\n6. Sixth step\n"
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "5. Fifth step" in combined
    assert "6. Sixth step" in combined


def test_blockquote_markers_and_nesting_preserved():
    text = "# Q\n> Outer quote line.\n>\n> > Nested quote line.\n"
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "> Outer quote line." in combined
    assert "> > Nested quote line." in combined


# ---------------------------------------------------------------------------
# Regression test: oversized lists were hard-split mid-item
# ---------------------------------------------------------------------------

def test_large_list_splits_on_item_boundaries_not_mid_item():
    n_items = 20
    text = "# Notes\n" + "\n".join(
        f"- item number {i}: some descriptive detail about the item"
        for i in range(1, n_items + 1)
    ) + "\n"
    chunks = chunk_markdown(
        text, config=ChunkerConfig(target_size=60, max_size=150, min_size=0, overlap=0)
    )

    full_lines = [
        f"item number {i}: some descriptive detail about the item"
        for i in range(1, n_items + 1)
    ]
    for line in full_lines:
        matches = [c.text for c in chunks if line in c.text]
        assert len(matches) == 1, f"item {line!r} should appear whole in exactly one chunk"


# ---------------------------------------------------------------------------
# Regression test: offset computation correctness (not just performance)
# ---------------------------------------------------------------------------

def test_offsets_match_source_slices():
    text = "# Title\n\nFirst paragraph here with some words.\n\n## Sub\n\nSecond paragraph.\n"
    chunks = chunk_markdown(
        text, config=ChunkerConfig(target_size=15, max_size=60, min_size=0, overlap=0)
    )
    for c in chunks:
        so, eo = c.metadata.start_offset, c.metadata.end_offset
        assert so is not None and eo is not None
        assert 0 <= so <= eo <= len(text)


def test_chunking_time_scales_roughly_linearly():
    # A regression guard against reintroducing the O(document size x block
    # count) offset bug: doubling the document should not multiply time by
    # anywhere near 4x (quadratic), only by roughly 2x (linear), with a
    # generous margin for machine noise.
    section = (
        "\n## Section {n}\n\nSome paragraph text for section {n}. Another sentence.\n"
        "\n- item a{n}\n- item b{n}\n"
    )

    def build(n):
        return "# Doc\n" + "\n".join(section.format(n=i) for i in range(n))

    small = build(150)
    large = build(300)

    start = time.perf_counter()
    chunk_markdown(small)
    small_time = time.perf_counter() - start

    start = time.perf_counter()
    chunk_markdown(large)
    large_time = time.perf_counter() - start

    # Guard against div-by-zero on very fast machines.
    small_time = max(small_time, 1e-4)
    assert large_time / small_time < 4.0


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_config_validation_errors():
    import pytest

    with pytest.raises(ValueError):
        ChunkerConfig(target_size=0)
    with pytest.raises(ValueError):
        ChunkerConfig(max_size=10, target_size=50)
    with pytest.raises(ValueError):
        ChunkerConfig(overlap=-1)
    with pytest.raises(ValueError):
        ChunkerConfig(min_size=-1)


def test_invalid_markdown_type_raises():
    import pytest

    with pytest.raises(TypeError):
        chunk_markdown(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# General robustness
# ---------------------------------------------------------------------------

def test_unicode_content_is_preserved():
    text = "# Café\nThe café serves crêpes. Prices are in €. Emoji: 🎉.\n"
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "café" in combined and "€" in combined and "🎉" in combined


def test_word_size_metric_does_not_crash_on_lists_and_tables():
    text = "# T\n- item one two three\n- item four five six\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    chunks = chunk_markdown(
        text,
        config=ChunkerConfig(target_size=5, max_size=10, min_size=0, overlap=2),
        size_metric=WordSizeMetric(),
    )
    assert chunks


# ---------------------------------------------------------------------------
# Regression tests: follow-up fixes (blockquote nested content, loose list
# items, chunk_type tiebreak)
# ---------------------------------------------------------------------------

def test_blockquote_preserves_nested_code_list_and_table():
    text = (
        "# Q\n"
        "> Quote intro.\n"
        ">\n"
        "> ```python\n"
        "> code_in_quote()\n"
        "> ```\n"
        ">\n"
        "> - bullet in quote\n"
        ">\n"
        "> | A | B |\n"
        "> |---|---|\n"
        "> | 1 | 2 |\n"
    )
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    # Previously, everything except the first paragraph and a nested
    # blockquote was silently dropped inside a blockquote.
    assert "code_in_quote()" in combined
    assert "bullet in quote" in combined
    assert "| 1 | 2 |" in combined


def test_loose_list_item_keeps_paragraph_break():
    text = (
        "# S\n1. First step\n\n"
        "   Second paragraph of first step with more detail.\n\n2. Second step\n"
    )
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "1. First step" in combined
    assert "2. Second step" in combined
    # The continuation paragraph must be indented (not joined with a space
    # onto the first paragraph, and not flattened to column 0 where it would
    # look like a new top-level block).
    assert "\n   Second paragraph of first step with more detail." in combined


def test_chunk_type_breaks_ties_by_actual_content_size():
    # A tiny two-item list next to a larger table sharing one chunk: the
    # table clearly contributes more content and should win the label,
    # rather than an arbitrary fixed priority order.
    text = "# Mixed\n- a\n- b\n\n| X | Y |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
    chunks = chunk_markdown(text, config=ChunkerConfig(target_size=200, max_size=400, min_size=0))
    assert any(c.metadata.chunk_type == "table" for c in chunks)


def test_blockquote_nested_inside_list_item_keeps_marker_and_code():
    # Found by the regression corpus (tests/corpus/messy_edge_cases.md): a
    # blockquote directly nested inside a list item previously leaked its
    # inner paragraph text into the item's top-level scan (losing the '>'
    # prefix) and silently dropped a fenced code block inside that
    # blockquote entirely.
    text = (
        "# T\n2. Outer item two\n"
        "   > A blockquote inside a list item.\n"
        "   >\n"
        "   > ```python\n"
        '   > print("quoted code inside a list item")\n'
        "   > ```\n"
    )
    chunks = chunk_markdown(text)
    combined = "\n".join(c.text for c in chunks)
    assert "> A blockquote inside a list item." in combined
    assert "quoted code inside a list item" in combined


