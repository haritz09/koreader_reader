from pathlib import Path

import pytest

from adapters.storage.image_media_type import cover_media_type


@pytest.mark.parametrize(
	("header", "expected"),
	[
		(b"\x89PNG\r\n\x1a\n", "image/png"),
		(b"GIF89a", "image/gif"),
		(b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
		(b"\xff\xd8\xff\xe0", "image/jpeg"),
	],
)
def test_cover_media_type_sniffs_the_file_header(
	tmp_path: Path,
	header: bytes,
	expected: str,
) -> None:
	cover = tmp_path / "cover"
	cover.write_bytes(header + b"\x00" * 16)

	assert cover_media_type(cover) == expected
