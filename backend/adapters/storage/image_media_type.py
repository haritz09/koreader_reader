from pathlib import Path


def cover_media_type(path: Path) -> str:
	with path.open("rb") as stream:
		header = stream.read(12)
	if header.startswith(b"\x89PNG\r\n\x1a\n"):
		return "image/png"
	if header.startswith(b"GIF8"):
		return "image/gif"
	if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
		return "image/webp"
	return "image/jpeg"
