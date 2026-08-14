"""Structure-aware Markdown chunking for RAG systems."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .metrics import CharacterSizeMetric, SizeMetric
from .models import Chunk, ChunkMetadata

CHUNK_TEXT = "text"
CHUNK_TABLE = "table"
CHUNK_CODE = "code"
CHUNK_LIST = "list"
CHUNK_BLOCKQUOTE = "blockquote"
CHUNK_HTML = "html"

_ATOMIC_KINDS = (CHUNK_TABLE, CHUNK_CODE, CHUNK_LIST, CHUNK_BLOCKQUOTE, CHUNK_HTML)


@lru_cache(maxsize=8)
def _compile_sentence_pattern(abbreviations: Tuple[str, ...]) -> "re.Pattern[str]":
    """Compile the sentence-boundary regex once per distinct abbreviation
    set (in practice just once, since the default set never changes) and
    cache it. Cached via `lru_cache` rather than a hand-rolled dynamic class
    attribute so the return type stays statically known.

    Python's `re` module requires a lookbehind's alternatives to all be the
    same length, so protecting "Mr.", "Mrs.", "Prof.", etc. cannot be done
    with one alternation -- each abbreviation (and the single-capital-letter
    "initial" pattern, e.g. the "J." in "J. R. R. Tolkien") is instead its
    own separate fixed-width negative lookbehind, chained together.
    """
    lookbehinds = "".join(rf"(?<!\b{re.escape(abbr)})" for abbr in abbreviations)
    lookbehinds += r"(?<!\b[A-Z]\.)"
    # A sentence boundary is: terminal punctuation, optionally followed by a
    # closing quote/bracket, then whitespace, then an uppercase letter or
    # digit -- unless that punctuation was actually part of a protected
    # abbreviation/initial (the lookbehinds above) or is a decimal point
    # sitting between two digits (already excluded since \s+ requires actual
    # whitespace between the digits).
    return re.compile(lookbehinds + r"(?<=[.!?])(?:[\"')\]]*)\s+(?=[A-Z0-9])")


@dataclass(frozen=True, slots=True)
class ChunkerConfig:
    """Configuration for :class:`MarkdownChunker`."""

    target_size: int = 700
    max_size: int = 1000
    overlap: int = 100
    min_size: int = 300
    include_headings: bool = True
    include_heading_path: bool = True
    preserve_tables: bool = True
    preserve_code_blocks: bool = True
    preserve_lists: bool = True
    preserve_blockquotes: bool = True
    preserve_html_blocks: bool = True

    def __post_init__(self) -> None:
        if self.min_size < 0:
            raise ValueError("min_size must be >= 0")
        if self.target_size <= 0:
            raise ValueError("target_size must be > 0")
        if self.max_size < self.target_size:
            raise ValueError("max_size must be >= target_size")
        if self.overlap < 0:
            raise ValueError("overlap must be >= 0")


@dataclass(slots=True)
class _Block:
    kind: str
    text: str
    heading_path: Tuple[str, ...]
    start_line: Optional[int]
    end_line: Optional[int]
    start_offset: Optional[int]
    end_offset: Optional[int]
    splittable: bool = True


@dataclass(slots=True)
class _Draft:
    parts: List[str] = field(default_factory=list)
    blocks: List[_Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.strip() for p in self.parts if p.strip()).strip()


class MarkdownChunker:
    """Parse Markdown and create structure-aware RAG chunks.

    The implementation is deliberately independent of embedding models,
    vector stores, LLMs, and RAG frameworks.
    """

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        *,
        size_metric: Optional[SizeMetric] = None,
    ) -> None:
        self.config = config or ChunkerConfig()
        self.metric = size_metric or CharacterSizeMetric()
        # "table" is disabled by the commonmark preset (GFM tables are not
        # part of vanilla CommonMark) but is built into markdown-it-py, so
        # no extra dependency is needed to support them.
        self._parser = MarkdownIt("commonmark", {"html": True}).enable("table")

    def chunk(self, markdown: str) -> List[Chunk]:
        """Chunk a Markdown document into RAG-ready :class:`Chunk` objects."""
        if not isinstance(markdown, str):
            raise TypeError("markdown must be a string")
        if not markdown.strip():
            return []

        source = self._normalize_newlines(markdown)
        tokens = self._parser.parse(source)
        line_offsets = self._line_offsets(source)
        blocks = self._tokens_to_blocks(tokens, line_offsets)
        drafts = self._chunk_blocks(blocks)

        return self._finalize(drafts)

    def _normalize_newlines(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _line_offsets(source: str) -> List[int]:
        """Character offset of the start of each line, computed once per
        document. `_offset`/`_end_offset` then look this up in O(1) instead
        of each re-running `splitlines()` over the whole source and summing
        line lengths from scratch -- which previously made offset tracking
        cost O(document size x block count) instead of O(document size)."""
        offsets = [0]
        for line in source.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        return offsets

    def _tokens_to_blocks(
        self, tokens: Sequence[Token], line_offsets: Sequence[int]
    ) -> List[_Block]:
        blocks: List[_Block] = []
        heading_stack: List[str] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                level = int(token.tag[1:])
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                title = self._inline_text(inline) if inline else ""
                title = self._clean_inline(title)

                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(title)

                if self.config.include_headings and title:
                    blocks.append(
                        _Block(
                            kind="heading",
                            text=title,
                            heading_path=tuple(heading_stack),
                            start_line=self._line(token),
                            end_line=self._end_line(token),
                            start_offset=self._offset(token, line_offsets),
                            end_offset=self._end_offset(token, line_offsets),
                            splittable=False,
                        )
                    )
                i += 3
                continue

            if token.type in {"paragraph_open", "blockquote_open", "bullet_list_open",
                              "ordered_list_open", "fence", "code_block", "table_open",
                              "html_block"}:
                block, consumed = self._parse_block(tokens, i, tuple(heading_stack), line_offsets)
                if block and block.text.strip():
                    blocks.append(block)
                i += consumed
                continue

            i += 1

        return blocks

    def _parse_block(
        self,
        tokens: Sequence[Token],
        index: int,
        path: Tuple[str, ...],
        line_offsets: Sequence[int],
    ) -> Tuple[Optional[_Block], int]:
        token = tokens[index]

        if token.type in {"fence", "code_block"}:
            text = token.content.rstrip()
            return self._make_block(
                CHUNK_CODE, text, path, token, line_offsets,
                not self.config.preserve_code_blocks,
            ), 1

        if token.type == "html_block":
            text = token.content.rstrip()
            return self._make_block(
                CHUNK_HTML, text, path, token, line_offsets,
                not self.config.preserve_html_blocks,
            ), 1

        if token.type == "paragraph_open":
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            text = self._inline_text(inline) if inline else ""
            return self._make_block(
                "text", self._clean_inline(text), path, token, line_offsets, True
            ), 3

        if token.type == "blockquote_open":
            end = self._find_matching_close(tokens, index, "blockquote_close")
            text = self._render_blockquote(tokens[index:end + 1])
            return self._make_block(
                CHUNK_BLOCKQUOTE, text, path, token, line_offsets,
                not self.config.preserve_blockquotes,
            ), end - index + 1

        if token.type in {"bullet_list_open", "ordered_list_open"}:
            close = self._list_close_type(token.type)
            end = self._find_matching_close(tokens, index, close)
            text = "\n".join(self._render_list_items(tokens[index:end + 1]))
            return self._make_block(
                CHUNK_LIST, text, path, token, line_offsets, not self.config.preserve_lists
            ), end - index + 1

        if token.type == "table_open":
            end = self._find_matching_close(tokens, index, "table_close")
            text = self._table_text(tokens[index:end + 1])
            return self._make_block(
                CHUNK_TABLE, text, path, token, line_offsets, not self.config.preserve_tables
            ), end - index + 1

        return None, 1

    def _make_block(
        self, kind: str, text: str, path: Tuple[str, ...],
        token: Token, line_offsets: Sequence[int], splittable: bool
    ) -> _Block:
        return _Block(
            kind=kind,
            text=text.strip(),
            heading_path=path,
            start_line=self._line(token),
            end_line=self._end_line(token),
            start_offset=self._offset(token, line_offsets),
            end_offset=self._end_offset(token, line_offsets),
            splittable=splittable,
        )

    def _chunk_blocks(self, blocks: Sequence[_Block]) -> List[_Draft]:
        drafts: List[_Draft] = []
        current = _Draft()

        def flush() -> None:
            nonlocal current
            if current.text:
                drafts.append(current)
            current = _Draft()

        for block in blocks:
            # Major headings create semantic boundaries.
            if block.kind == "heading":
                if current.text and self.metric.measure(current.text) >= self.config.min_size:
                    flush()
                current.parts.append(block.text)
                current.blocks.append(block)
                continue

            if block.kind in _ATOMIC_KINDS and not block.splittable:
                block_size = self.metric.measure(block.text)
                current_size = self.metric.measure(current.text) if current.text else 0
                if current.text and current_size + block_size > self.config.max_size:
                    flush()

                if block_size <= self.config.max_size:
                    current.parts.append(block.text)
                    current.blocks.append(block)
                else:
                    # Large atomic blocks are split only as a last resort.
                    if current.text:
                        flush()
                    for piece in self._split_oversized_block(block):
                        drafts.append(
                            _Draft(parts=[piece], blocks=[block])
                        )
                continue

            # Normal prose.
            for piece in self._split_text(block.text):
                if not piece:
                    continue
                candidate = piece if not current.text else f"{current.text}\n\n{piece}"
                if current.text and self.metric.measure(candidate) > self.config.max_size:
                    flush()
                current.parts.append(piece)
                current.blocks.append(block)

                if self.metric.measure(current.text) >= self.config.target_size:
                    flush()

        flush()
        return drafts

    def _split_text(self, text: str) -> Iterable[str]:
        sentences = self._sentences(text)
        if not sentences:
            return [text.strip()]

        pieces: List[str] = []
        current: List[str] = []

        for sentence in sentences:
            candidate = " ".join([*current, sentence]).strip()
            if current and self.metric.measure(candidate) > self.config.max_size:
                pieces.append(" ".join(current).strip())
                current = [sentence]
            elif not current and self.metric.measure(sentence) > self.config.max_size:
                pieces.extend(self._hard_split(sentence))
                current = []
            else:
                current.append(sentence)

        if current:
            pieces.append(" ".join(current).strip())
        return pieces

    def _split_oversized_block(self, block: _Block) -> Iterable[str]:
        if block.kind == CHUNK_TABLE:
            return self._split_table(block.text)
        if block.kind == CHUNK_LIST:
            return self._split_list(block.text)
        return self._hard_split(block.text)

    def _split_table(self, text: str) -> List[str]:
        rows = [line for line in text.splitlines() if line.strip()]
        if len(rows) <= 2:
            return self._hard_split(text)

        header = rows[:2]
        chunks: List[str] = []
        current = list(header)

        for row in rows[2:]:
            candidate = "\n".join([*current, row])
            if len(current) > 2 and self.metric.measure(candidate) > self.config.max_size:
                chunks.append("\n".join(current))
                current = list(header)
            current.append(row)

        if len(current) > 2:
            chunks.append("\n".join(current))
        return chunks or [text]

    def _split_list(self, text: str) -> List[str]:
        # Rendered list text (see _render_list_items) always starts each
        # top-level item at column 0, with any nested content indented
        # beneath it. That makes a fresh, unindented line a reliable item
        # boundary, so items -- including their nested sub-items -- can be
        # grouped up to max_size as atomic units instead of being cut
        # mid-item by a character-level split.
        lines = text.splitlines()
        items: List[str] = []
        current_item: List[str] = []
        for line in lines:
            if line[:1] not in ("", " ") and current_item:
                items.append("\n".join(current_item))
                current_item = [line]
            else:
                current_item.append(line)
        if current_item:
            items.append("\n".join(current_item))

        if len(items) <= 1:
            return self._hard_split(text)

        pieces: List[str] = []
        current: List[str] = []
        for item in items:
            candidate = "\n".join([*current, item])
            if current and self.metric.measure(candidate) > self.config.max_size:
                pieces.append("\n".join(current))
                current = [item]
            else:
                current.append(item)
        if current:
            pieces.append("\n".join(current))

        # A single item that alone exceeds max_size still needs a last-resort
        # character split, but only for that one oversized item.
        final: List[str] = []
        for piece in pieces:
            if self.metric.measure(piece) <= self.config.max_size:
                final.append(piece)
            else:
                final.extend(self._hard_split(piece))
        return final or [text]

    def _hard_split(self, text: str) -> List[str]:
        max_size = self.config.max_size
        if self.metric.measure(text) <= max_size:
            return [text.strip()]

        if not isinstance(self.metric, CharacterSizeMetric):
            # Generic metrics cannot safely map a metric budget to character
            # offsets; fall back to whitespace chunks.
            words = text.split()
            pieces, current = [], []  # type: List[str], List[str]
            for word in words:
                candidate = " ".join([*current, word])
                if current and self.metric.measure(candidate) > max_size:
                    pieces.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                pieces.append(" ".join(current))
            return pieces

        pieces = []
        start = 0
        while start < len(text):
            end = min(start + max_size, len(text))
            if end < len(text):
                boundary = max(
                    text.rfind("\n", start, end),
                    text.rfind(" ", start, end),
                )
                if boundary > start:
                    end = boundary
            pieces.append(text[start:end].strip())
            start = end
            while start < len(text) and text[start].isspace():
                start += 1
        return pieces

    # Abbreviations that should not be treated as sentence-ending, keyed by
    # their fixed-width text (including the trailing period) so each can be
    # used as its own fixed-width lookbehind. Python's `re` module rejects a
    # single lookbehind whose alternatives have different lengths (e.g. "Mr"
    # vs. "Prof"), so these are compiled as separate chained lookbehinds
    # instead of one alternation.
    _ABBREVIATIONS: Tuple[str, ...] = (
        "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.",
        "vs.", "e.g.", "i.e.", "etc.", "approx.", "no.", "No.",
        "a.m.", "p.m.", "cf.", "al.",
    )

    def _sentence_pattern(self) -> "re.Pattern[str]":
        return _compile_sentence_pattern(self._ABBREVIATIONS)

    def _sentences(self, text: str) -> List[str]:
        # Conservative English sentence splitting. It avoids splitting common
        # abbreviations and initials in ordinary prose. Decimal numbers (e.g.
        # "3.14") are unaffected because there is never whitespace between
        # the digits.
        pattern = self._sentence_pattern()
        return [x.strip() for x in pattern.split(text) if x.strip()]

    def _finalize(self, drafts: Sequence[_Draft]) -> List[Chunk]:
        result: List[Chunk] = []
        prefixes: List[str] = []
        for draft in drafts:
            text = draft.text
            if not text:
                continue

            paths = self._merge_paths(draft.blocks)
            prefix = ""
            if self.config.include_heading_path and paths:
                prefix = "\n".join(" > ".join(path) for path in paths)
                if prefix and text.startswith(prefix):
                    pass  # already present verbatim (e.g. heading block itself)
                elif prefix:
                    text = f"{prefix}\n\n{text}"

            start_line = min((b.start_line for b in draft.blocks if b.start_line), default=None)
            end_line = max((b.end_line for b in draft.blocks if b.end_line), default=None)
            start_offset = min(
                (b.start_offset for b in draft.blocks if b.start_offset is not None), default=None
            )
            end_offset = max(
                (b.end_offset for b in draft.blocks if b.end_offset is not None), default=None
            )

            kind = self._chunk_type(draft)
            index = len(result) + 1

            metadata = ChunkMetadata(
                chunk_id=f"c{index}",
                chunk_index=index,
                chunk_type=kind,
                heading_path=paths[0] if paths else (),
                start_line=start_line,
                end_line=end_line,
                start_offset=start_offset,
                end_offset=end_offset,
                size=self.metric.measure(text),
                size_metric=self.metric.name,
            )
            result.append(Chunk(text=text, metadata=metadata))
            prefixes.append(prefix if text.startswith(prefix) else "")

        return self._apply_overlap(result, prefixes)

    def _apply_overlap(self, chunks: List[Chunk], prefixes: List[str]) -> List[Chunk]:
        if self.config.overlap <= 0 or len(chunks) < 2:
            return chunks

        result: List[Chunk] = [chunks[0]]
        for i in range(1, len(chunks)):
            previous, current = chunks[i - 1], chunks[i]
            if previous.metadata.heading_path != current.metadata.heading_path:
                result.append(current)
                continue

            # Draw the overlap tail from the previous chunk's own body only
            # -- never from its heading-path breadcrumb, which the current
            # chunk already carries as its own prefix. Otherwise a chunk
            # that is *only* a heading label (no body prose yet) ends up
            # having its entire text duplicated onto the next chunk.
            prev_body = previous.text
            prev_prefix = prefixes[i - 1]
            if prev_prefix and prev_body.startswith(prev_prefix):
                prev_body = prev_body[len(prev_prefix):].lstrip("\n")

            tail = self._overlap_tail(prev_body)
            if not tail:
                result.append(current)
                continue

            text = f"{tail}\n\n{current.text}"
            if self.metric.measure(text) > self.config.max_size:
                result.append(current)
                continue

            meta = ChunkMetadata(
                chunk_id=current.metadata.chunk_id,
                chunk_index=current.metadata.chunk_index,
                chunk_type=current.metadata.chunk_type,
                heading_path=current.metadata.heading_path,
                start_line=current.metadata.start_line,
                end_line=current.metadata.end_line,
                start_offset=current.metadata.start_offset,
                end_offset=current.metadata.end_offset,
                size=self.metric.measure(text),
                size_metric=self.metric.name,
                extra=current.metadata.extra,
            )
            result.append(Chunk(text=text, metadata=meta))
        return result

    def _overlap_tail(self, text: str) -> str:
        if not isinstance(self.metric, CharacterSizeMetric):
            return ""
        sentences = self._sentences(text)
        if not sentences:
            return ""
        selected: List[str] = []
        total = 0
        for sentence in reversed(sentences):
            selected.insert(0, sentence)
            total += len(sentence) + 1
            if total >= self.config.overlap:
                break
        return " ".join(selected).strip()

    @staticmethod
    def _merge_paths(blocks: Sequence[_Block]) -> List[Tuple[str, ...]]:
        paths: List[Tuple[str, ...]] = []
        for block in blocks:
            if block.heading_path and (not paths or paths[-1] != block.heading_path):
                paths.append(block.heading_path)
        return paths

    def _chunk_type(self, draft: "_Draft") -> str:
        # `parts` and `blocks` are always parallel (one block per piece of
        # text that was appended), so this measures how much of the chunk's
        # actual content came from each block kind. Headings are excluded
        # entirely: a short title should never affect classification.
        sizes: Dict[str, int] = {}
        for part, block in zip(draft.parts, draft.blocks, strict=True):
            if block.kind == "heading":
                continue
            sizes[block.kind] = sizes.get(block.kind, 0) + self.metric.measure(part)

        # Plain prose never outranks a structured kind, regardless of size:
        # a one-line intro sentence next to a short code block should still
        # label the chunk "code", not "text". This is the fix for the
        # original bug (chunk_type silently falling back to "text" whenever
        # a heading or a little prose shared a chunk with real structure).
        structured = {kind: size for kind, size in sizes.items() if kind != CHUNK_TEXT}
        if structured:
            # When two or more different structured kinds genuinely coexist
            # in the same chunk (e.g. a small list and a small table both
            # fit together), break the tie by which one actually
            # contributes more content, rather than an arbitrary fixed
            # priority order a reader would have no way to predict.
            best_kind: str = max(structured, key=lambda kind: structured[kind])
            return best_kind
        return CHUNK_TEXT

    @staticmethod
    def _inline_text(token: Optional[Token]) -> str:
        if token is None:
            return ""
        return token.content or token.markup or ""

    def _render_blockquote(self, tokens: Sequence[Token]) -> str:
        """Reconstruct a blockquote_open .. blockquote_close token span into
        '> '-prefixed markdown, preserving nesting (each recursion level adds
        one more '> '). A blockquote can legally contain any other block
        type (paragraphs, code, lists, tables, HTML, nested blockquotes), so
        every block type is handled here rather than just plain paragraphs."""
        lines: List[str] = []
        i, n = 1, len(tokens) - 1
        while i < n:
            tok = tokens[i]
            if tok.type == "inline":
                lines.extend(tok.content.strip().splitlines())
                i += 1
            elif tok.type == "blockquote_open":
                end = self._find_matching_close(tokens, i, "blockquote_close")
                lines.extend(self._render_blockquote(tokens[i:end + 1]).splitlines())
                i = end + 1
            elif tok.type in {"fence", "code_block", "html_block"}:
                lines.extend(tok.content.rstrip().splitlines())
                i += 1
            elif tok.type in {"bullet_list_open", "ordered_list_open"}:
                close = self._list_close_type(tok.type)
                end = self._find_matching_close(tokens, i, close)
                for item in self._render_list_items(tokens[i:end + 1]):
                    lines.extend(item.splitlines())
                i = end + 1
            elif tok.type == "table_open":
                end = self._find_matching_close(tokens, i, "table_close")
                lines.extend(self._table_text(tokens[i:end + 1]).splitlines())
                i = end + 1
            else:
                i += 1
        return "\n".join(f"> {line}" if line else ">" for line in lines)

    def _render_list_items(self, tokens: Sequence[Token]) -> List[str]:
        """Reconstruct a bullet_list_open/ordered_list_open .. _close token
        span into a list of top-level item strings (marker + text, with any
        nested sub-list indented two spaces beneath it). Returning one string
        per top-level item -- rather than one flat joined string -- lets
        oversized lists later be split at item boundaries."""
        open_token = tokens[0]
        ordered = open_token.type == "ordered_list_open"
        number: Optional[int] = int((open_token.attrs or {}).get("start", 1)) if ordered else None
        marker_char = open_token.markup or ("-" if not ordered else ".")

        items: List[str] = []
        i, n = 1, len(tokens) - 1
        while i < n:
            tok = tokens[i]
            if tok.type == "list_item_open":
                end = self._find_matching_close(tokens, i, "list_item_close")
                marker = f"{number}{marker_char}" if ordered else marker_char
                items.append(self._render_list_item(tokens[i:end + 1], marker))
                if ordered:
                    assert number is not None
                    number += 1
                i = end + 1
            else:
                i += 1
        return items

    def _render_list_item(self, tokens: Sequence[Token], marker: str) -> str:
        """Render a single list_item_open .. list_item_close span. The
        item's own direct-child content comes first -- the first segment's
        first line on the marker's own line, everything else (further
        paragraphs of a loose item, or a directly-nested blockquote/code
        block/table/HTML block) as blank-line-separated continuation text
        indented to align under the marker -- followed by any nested list's
        items indented two spaces beneath it.

        Nested sub-lists are always rendered last, after all other content,
        regardless of where they actually appeared among the item's other
        children; exact interleaving order between a nested sub-list and
        other nested block types is not preserved. This matches the same
        simplification already made for multi-paragraph continuation
        content and is rare enough in practice not to warrant a full
        document-order-preserving rewrite here."""
        segments: List[str] = []
        sub_lines: List[str] = []
        i, n = 1, len(tokens) - 1
        while i < n:
            tok = tokens[i]
            if tok.type == "inline":
                text = tok.content.strip()
                if text:
                    segments.append(text)
                i += 1
            elif tok.type in {"bullet_list_open", "ordered_list_open"}:
                close = self._list_close_type(tok.type)
                end = self._find_matching_close(tokens, i, close)
                for nested_item in self._render_list_items(tokens[i:end + 1]):
                    sub_lines.extend("  " + line for line in nested_item.splitlines())
                i = end + 1
            elif tok.type == "blockquote_open":
                end = self._find_matching_close(tokens, i, "blockquote_close")
                rendered = self._render_blockquote(tokens[i:end + 1])
                if rendered:
                    segments.append(rendered)
                i = end + 1
            elif tok.type in {"fence", "code_block", "html_block"}:
                content = tok.content.rstrip()
                if content:
                    segments.append(content)
                i += 1
            elif tok.type == "table_open":
                end = self._find_matching_close(tokens, i, "table_close")
                rendered_table = self._table_text(tokens[i:end + 1])
                if rendered_table:
                    segments.append(rendered_table)
                i = end + 1
            else:
                i += 1

        if not segments:
            first_line = marker
            continuation_lines: List[str] = []
        else:
            first_segment_lines = segments[0].splitlines() or [""]
            first_line = f"{marker} {first_segment_lines[0]}".rstrip()
            # Everything after the first segment's first line -- whether
            # more lines of that same segment (e.g. a multi-line
            # blockquote as the item's very first piece of content) or
            # later segments entirely -- is blank-line separated (between
            # segments) and indented to align under the first line, so it
            # reads as a continuation of this item rather than a new item
            # (or a top-level block) when the list is later re-parsed for
            # oversized-list splitting in _split_list.
            continuation_indent = " " * (len(marker) + 1)
            continuation_lines = []
            for line in first_segment_lines[1:]:
                continuation_lines.append(continuation_indent + line if line else "")
            for segment in segments[1:]:
                continuation_lines.append("")
                for line in segment.splitlines():
                    continuation_lines.append(continuation_indent + line if line else "")

        return "\n".join([first_line, *continuation_lines, *sub_lines])

    @staticmethod
    def _clean_inline(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _table_text(tokens: Sequence[Token]) -> str:
        # markdown-it table tokens are easiest to reconstruct from their
        # inline cell contents while tracking rows. Column alignment is
        # carried on the header cells' `style` attribute (e.g.
        # "text-align:right") and is preserved in the rebuilt separator row
        # rather than being flattened to a plain "---" for every column.
        rows: List[str] = []
        alignments: List[str] = []
        current: List[str] = []
        header_done = False

        for token in tokens:
            if token.type == "tr_open":
                current = []
            elif token.type in {"th_open", "td_open"} and not header_done:
                style = str((token.attrs or {}).get("style", ""))
                if "text-align:right" in style:
                    alignments.append("right")
                elif "text-align:center" in style:
                    alignments.append("center")
                elif "text-align:left" in style:
                    alignments.append("left")
                else:
                    alignments.append("")
            elif token.type == "inline":
                current.append(token.content.strip())
            elif token.type == "tr_close":
                if current:
                    rows.append("| " + " | ".join(current) + " |")
                    current = []
                header_done = True

        if rows:
            columns = len(alignments) or (rows[0].count("|") - 1)
            markers = []
            for i in range(max(columns, 1)):
                align = alignments[i] if i < len(alignments) else ""
                markers.append(
                    {"left": ":---", "right": "---:", "center": ":---:"}.get(align, "---")
                )
            separator = "| " + " | ".join(markers) + " |"
            if len(rows) > 1:
                rows.insert(1, separator)
        return "\n".join(rows)

    @staticmethod
    def _find_matching_close(tokens: Sequence[Token], start: int, close_type: str) -> int:
        depth = 0
        open_type = tokens[start].type
        for i in range(start, len(tokens)):
            if tokens[i].type == open_type:
                depth += 1
            elif tokens[i].type == close_type:
                depth -= 1
                if depth == 0:
                    return i
        return len(tokens) - 1

    @staticmethod
    def _list_close_type(list_open_type: str) -> str:
        """The matching close-token type name for a bullet/ordered list_open."""
        return "bullet_list_close" if list_open_type == "bullet_list_open" else "ordered_list_close"

    @staticmethod
    def _line(token: Token) -> Optional[int]:
        return token.map[0] + 1 if token.map else None

    @staticmethod
    def _end_line(token: Token) -> Optional[int]:
        return token.map[1] if token.map else None

    @staticmethod
    def _offset(token: Token, line_offsets: Sequence[int]) -> Optional[int]:
        if not token.map:
            return None
        idx = token.map[0]
        return line_offsets[idx] if idx < len(line_offsets) else line_offsets[-1]

    @staticmethod
    def _end_offset(token: Token, line_offsets: Sequence[int]) -> Optional[int]:
        if not token.map:
            return None
        idx = token.map[1]
        return line_offsets[idx] if idx < len(line_offsets) else line_offsets[-1]


def chunk_markdown(
    markdown: str,
    *,
    config: Optional[ChunkerConfig] = None,
    size_metric: Optional[SizeMetric] = None,
) -> List[Chunk]:
    """Convenience API for chunking Markdown."""
    return MarkdownChunker(config=config, size_metric=size_metric).chunk(markdown)
