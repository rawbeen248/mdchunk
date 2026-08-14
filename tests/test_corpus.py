"""Regression-corpus tests.

Unlike test_basic.py (narrow, exact-output tests targeting one specific bug
each), these tests run the chunker against realistic, varied documents and
check invariants that should hold for ANY well-formed input, rather than
asserting exact expected output. This is what PROJECT_GUIDE.md section 16
calls a "regression corpus": the goal is to catch problems (crashes, silent
data loss, grossly broken size limits) that only show up on real documents,
which are messier than the minimal examples in test_basic.py.

Extend this by dropping more .md files into tests/corpus/ -- no test code
changes are needed, they are picked up automatically by every test in this
file except test_corpus_distinctive_content_is_not_silently_lost, which
checks specific known content per named file (see its docstring).
"""

from pathlib import Path

import pytest

from mdchunk import ChunkerConfig, chunk_markdown
from mdchunk.metrics import WordSizeMetric

CORPUS_DIR = Path(__file__).parent / "corpus"
CORPUS_FILES = sorted(CORPUS_DIR.glob("*.md"))
CORPUS_FILENAMES = [p.name for p in CORPUS_FILES]

CONFIGS = {
    "default": ChunkerConfig(),
    "tiny": ChunkerConfig(target_size=20, max_size=50, min_size=0, overlap=5),
    "no_overlap": ChunkerConfig(target_size=100, max_size=250, min_size=0, overlap=0),
    "huge": ChunkerConfig(target_size=5000, max_size=10000, min_size=0),
}


@pytest.fixture(scope="module")
def corpus_texts():
    assert CORPUS_FILES, "tests/corpus/ should contain at least one .md file"
    return {path.name: path.read_text(encoding="utf-8") for path in CORPUS_FILES}


@pytest.mark.parametrize("config_name", sorted(CONFIGS))
@pytest.mark.parametrize("filename", CORPUS_FILENAMES)
def test_corpus_document_does_not_crash(corpus_texts, filename, config_name):
    text = corpus_texts[filename]
    chunks = chunk_markdown(text, config=CONFIGS[config_name])
    assert chunks, f"{filename} ({config_name}) produced no chunks"


@pytest.mark.parametrize("filename", CORPUS_FILENAMES)
def test_corpus_chunks_are_non_empty(corpus_texts, filename):
    text = corpus_texts[filename]
    for config_name, config in CONFIGS.items():
        chunks = chunk_markdown(text, config=config)
        for c in chunks:
            assert c.text.strip(), f"{filename} ({config_name}) produced an empty chunk"


@pytest.mark.parametrize("filename", CORPUS_FILENAMES)
def test_corpus_heading_paths_are_real_headings(corpus_texts, filename):
    # Every heading_path segment should be text that genuinely appears in
    # the source document -- catches heading-tracking bugs (wrong level,
    # stale stack entries, etc.) without needing an exact expected list.
    text = corpus_texts[filename]
    chunks = chunk_markdown(text, config=CONFIGS["default"])
    for c in chunks:
        for segment in c.metadata.heading_path:
            assert segment in text, (
                f"{filename}: heading_path segment {segment!r} not found verbatim in source"
            )


@pytest.mark.parametrize("filename", CORPUS_FILENAMES)
def test_corpus_chunk_sizes_are_reasonably_bounded(corpus_texts, filename):
    # A loose bound, not a strict max_size check: a single atomic piece
    # (e.g. one very long table row, or one very long "word" with no break
    # point) can legitimately exceed max_size somewhat. This checks for
    # GROSSLY broken splitting (e.g. a regression back to returning the
    # whole document as one chunk) rather than exact compliance, which
    # test_basic.py already covers with clean, minimal inputs.
    text = corpus_texts[filename]
    config = ChunkerConfig(target_size=100, max_size=250, min_size=0, overlap=0)
    chunks = chunk_markdown(text, config=config)
    slack = config.max_size * 3
    for c in chunks:
        assert c.metadata.size <= slack, (
            f"{filename}: chunk of size {c.metadata.size} "
            f"grossly exceeds max_size={config.max_size}"
        )


@pytest.mark.parametrize("filename", CORPUS_FILENAMES)
def test_corpus_word_size_metric_does_not_crash(corpus_texts, filename):
    text = corpus_texts[filename]
    chunks = chunk_markdown(
        text,
        config=ChunkerConfig(target_size=30, max_size=80, min_size=0, overlap=5),
        size_metric=WordSizeMetric(),
    )
    assert chunks


def test_corpus_distinctive_content_is_not_silently_lost(corpus_texts):
    # Spot-checks specific strings per corpus document that earlier bugs
    # specifically dropped or mangled (HTML blocks, code nested inside a
    # blockquote, table cells, list items) to catch a regression back to
    # silent data loss on realistic documents, not just the minimal
    # test_basic.py cases. If you add a new corpus file, adding entries
    # here is optional -- the other tests in this module already cover it.
    expectations = {
        "api_reference.md": [
            "curl https://api.example.com/v1/widgets",
            "| `limit` | integer | No | 20 | Maximum 100 |",
            "enqueue a replication event",
            "`metadata` values are stored as opaque JSON",
        ],
        "policy_faq.md": [
            "Content data | Indefinite | 30 days | +90 days",
            'Click "Request export"',
            "custom Data Processing Addendum (DPA)",
        ],
        "messy_edge_cases.md": [
            "quoted code inside a list item",
            "Raw HTML block with **markdown-looking** text",
            "café, naïve, jalapeño",
        ],
    }
    for filename, needles in expectations.items():
        text = corpus_texts[filename]
        chunks = chunk_markdown(
            text, config=ChunkerConfig(target_size=150, max_size=400, min_size=0)
        )
        combined = "\n".join(c.text for c in chunks)
        for needle in needles:
            assert needle in combined, (
                f"{filename}: expected content {needle!r} missing from output"
            )
