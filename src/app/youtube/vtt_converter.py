"""Convert VTT transcripts to plain text."""


def vtt_to_text(vtt_content: str) -> str:
    """Convert VTT transcript to plain speech text with paragraph breaks."""
    lines = vtt_content.strip().split("\n")
    paragraphs = []
    current_paragraph = []

    for line in lines:
        line = line.strip()

        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph))
                current_paragraph = []
            continue

        if line.startswith("WEBVTT"):
            continue

        if "-->" in line:
            continue

        # Skip metadata lines like "Kind: captions"
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2 and " " not in parts[0].strip():
                continue

        if line.isdigit():
            continue

        current_paragraph.append(line)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph))

    return "\n\n".join(paragraphs)
