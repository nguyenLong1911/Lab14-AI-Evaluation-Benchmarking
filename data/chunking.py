"""
Chia knowledge_base.txt thành các chunks theo từng section (## heading).
Output: chunks.jsonl — mỗi dòng là một JSON object với chunk_id, heading, content.
"""

import json
import re
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "knowledge_base.txt"
OUTPUT_FILE = Path(__file__).parent / "chunks.jsonl"


def chunk_by_section(text: str) -> list[dict]:
    """Split markdown text into chunks at each ## heading."""
    # Split on lines that start with '## '
    pattern = re.compile(r"(?=^## )", re.MULTILINE)
    raw_chunks = pattern.split(text)

    chunks = []
    # First item before any ## heading (document title / preamble)
    preamble = raw_chunks[0].strip()
    if preamble:
        title_match = re.match(r"^#\s+(.+)", preamble)
        chunks.append(
            {
                "chunk_id": "chunk_0",
                "heading": title_match.group(1).strip() if title_match else "Preamble",
                "content": preamble,
            }
        )

    for idx, block in enumerate(raw_chunks[1:], start=1):
        block = block.strip()
        if not block:
            continue
        heading_match = re.match(r"^##\s+(.+)", block)
        heading = heading_match.group(1).strip() if heading_match else f"Section {idx}"
        chunks.append(
            {
                "chunk_id": f"chunk_{idx}",
                "heading": heading,
                "content": block,
            }
        )

    return chunks


def main():
    text = INPUT_FILE.read_text(encoding="utf-8")
    chunks = chunk_by_section(text)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"Created {len(chunks)} chunks -> {OUTPUT_FILE}")
    for c in chunks:
        preview = c["content"][:60].replace("\n", " ").encode("ascii", "replace").decode()
        heading = c["heading"].encode("ascii", "replace").decode()
        print(f"  [{c['chunk_id']}] {heading!r}: {preview}...")


if __name__ == "__main__":
    main()
