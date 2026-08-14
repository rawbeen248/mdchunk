from mdchunker import chunk_markdown

markdown = """
# Authentication

Users must authenticate before accessing the API.

## API keys

API keys identify an application and should be stored securely.

## Rotation

Keys should be rotated regularly.
"""

chunks = chunk_markdown(markdown)

for chunk in chunks:
    print(chunk.metadata.chunk_id)
    print(chunk.metadata.heading_path)
    print(chunk.text)
    print("-" * 60)
