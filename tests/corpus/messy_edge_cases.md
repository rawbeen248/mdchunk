# Notes Dump

Random collection of notes. Formatting is inconsistent on purpose -- this
file exists to stress-test the chunker against things real documents
actually contain, not idealized markdown.

### Skipped heading level

The above heading jumps from H1 straight to H3 with no H2 in between. This
happens all the time in real documents (someone reformats and forgets to
fix levels).

## Back to H2

Some prose with escaped characters: \*not bold\*, \_not italic\_, \`not
code\`. And a literal backslash at the end of a line: C:\Users\name\.

Unicode stress: café, naïve, jalapeño, Zürich, Ελληνικά, 日本語, 한국어,
Русский, العربية, emoji 🎉🍰🚀, and a right-to-left mark test.

## A very long line

This paragraph intentionally contains one extremely long run-on sentence with no punctuation at all just to see what happens when the sentence splitter has nothing to latch onto and the size limit forces a hard split somewhere in the middle of all these words which just keep going and going without a single period or comma anywhere in sight until finally right here.

## URLs and abbreviations mixed together

Dr. Smith, J. R. Alvarez, and Prof. Lee (see https://example.com/team) all
reviewed this at 9 a.m. i.e. before the 10 a.m. standup. cf. the meeting
notes from Jan. 3rd, 2026. Contact them via support@example.com.

## Nested everything

1. Outer item one

   With a continuation paragraph.

   - inner bullet A
   - inner bullet B
     1. deeply nested ordered one
     2. deeply nested ordered two

2. Outer item two
   > A blockquote inside a list item.
   >
   > ```python
   > print("quoted code inside a list item")
   > ```

## Table with empty-ish cells

| A | B | C |
|---|---|---|
| 1 |   | 3 |
|   | 5 |   |

## Code block without a language tag

```
plain fenced block
no language hint
```

## Empty section

## Another empty section right after

## HTML mixed with markdown

<div class="note">
Raw HTML block with **markdown-looking** text inside it (should stay literal).
</div>

Regular paragraph immediately after the HTML block, no blank line quirks.

## Consecutive headings with minimal content

### H3 one
### H3 two
### H3 three

Content finally shows up here, after three headings in a row.
