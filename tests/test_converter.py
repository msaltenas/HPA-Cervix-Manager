"""Tests for images.converter. No network access -- uses synthetic in-memory images."""

import io

from PIL import Image

from images import converter


def _png_bytes(mode: str, size: tuple[int, int] = (40, 30)) -> bytes:
    img = Image.new(mode, size, (10, 20, 30, 128) if mode == "RGBA" else (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_convert_rgb_png_to_real_jpeg(tmp_path) -> None:
    dest = tmp_path / "HPA_000001.jpg"
    result = converter.convert_to_jpeg(_png_bytes("RGB"), dest)

    assert dest.exists()
    assert result.original_format == "PNG"
    assert result.width == 40
    assert result.height == 30
    assert result.file_size == dest.stat().st_size
    assert result.file_size > 0

    with Image.open(dest) as reopened:
        reopened.load()
        assert reopened.format == "JPEG"
        assert reopened.mode == "RGB"


def test_convert_rgba_png_flattens_alpha_onto_white(tmp_path) -> None:
    dest = tmp_path / "HPA_000002.jpg"
    result = converter.convert_to_jpeg(_png_bytes("RGBA"), dest)

    assert dest.exists()
    assert result.original_format == "PNG"

    with Image.open(dest) as reopened:
        reopened.load()
        assert reopened.mode == "RGB"
        # No alpha channel survives in JPEG output.
        assert "A" not in reopened.getbands()


def test_convert_does_not_overwrite_existing_original(tmp_path) -> None:
    original = tmp_path / "not_touched.png"
    original.write_bytes(_png_bytes("RGB"))
    original_bytes_before = original.read_bytes()

    dest = tmp_path / "HPA_000003.jpg"
    converter.convert_to_jpeg(original.read_bytes(), dest)

    assert original.read_bytes() == original_bytes_before
    assert dest != original
