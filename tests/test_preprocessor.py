"""Unit tests for the image preprocessing service."""

import io
import pytest
from PIL import Image, ImageDraw

from app.services.preprocessor import (
    ImagePreprocessor,
    InvalidImageError,
    CorruptImageError,
    OversizedImageError,
    UnsupportedFormatError,
)


def create_synthetic_image(
    format_name: str,
    width: int = 200,
    height: int = 100,
    mode: str = "RGB",
    color: tuple = (255, 255, 255),
    with_math_strokes: bool = False,
    exif_orientation: int = None,
) -> bytes:
    """Generate in-memory synthetic test images."""
    img = Image.new(mode, (width, height), color)
    draw = ImageDraw.Draw(img)

    if with_math_strokes:
        # Draw thin 1-pixel strokes simulating fraction bars, minus signs, and roots
        ink_color = (10, 10, 10) if mode != "RGBA" else (10, 10, 10, 255)
        # Fraction bar
        draw.line([(20, 50), (100, 50)], fill=ink_color, width=1)
        # Numerator dot / power
        draw.point([(60, 40), (61, 40)], fill=ink_color)
        # Denominator minus sign
        draw.line([(40, 65), (70, 65)], fill=ink_color, width=1)

    buffer = io.BytesIO()

    if exif_orientation and format_name.upper() == "JPEG":
        exif = img.getexif()
        exif[0x0112] = exif_orientation
        img.save(buffer, format=format_name, exif=exif)
    else:
        img.save(buffer, format=format_name)

    return buffer.getvalue()


class TestImagePreprocessor:
    """Test suite for ImagePreprocessor."""

    def test_valid_jpeg_processing(self):
        """Verify successful preprocessing of valid JPEG image."""
        raw_bytes = create_synthetic_image("JPEG", width=300, height=200, with_math_strokes=True)
        preprocessor = ImagePreprocessor()
        result = preprocessor.preprocess(raw_bytes)

        assert result.format == "JPEG"
        assert result.mime_type == "image/jpeg"
        assert result.original_dimensions == (300, 200)
        assert result.processed_dimensions == (300, 200)
        assert len(result.processed_bytes) > 0
        assert result.original_bytes == raw_bytes

    def test_valid_png_with_transparency(self):
        """Verify PNG with alpha transparency is composited over white background."""
        raw_bytes = create_synthetic_image("PNG", width=200, height=150, mode="RGBA", color=(0, 0, 0, 0), with_math_strokes=True)
        preprocessor = ImagePreprocessor()
        result = preprocessor.preprocess(raw_bytes)

        assert result.format == "PNG"
        assert result.mime_type == "image/png"
        assert result.processed_dimensions == (200, 150)

        # Inspect decoded result to verify background is white (255, 255, 255)
        decoded = Image.open(io.BytesIO(result.processed_bytes))
        assert decoded.mode == "RGB"
        corner_pixel = decoded.getpixel((0, 0))
        assert corner_pixel == (255, 255, 255)

    def test_valid_webp_processing(self):
        """Verify WEBP format support and preprocessing."""
        raw_bytes = create_synthetic_image("WEBP", width=250, height=180)
        preprocessor = ImagePreprocessor()
        result = preprocessor.preprocess(raw_bytes)

        assert result.format == "WEBP"
        assert result.mime_type == "image/webp"
        assert result.processed_dimensions == (250, 180)

    def test_empty_bytes_raises_invalid_image_error(self):
        """Verify empty byte sequence raises InvalidImageError."""
        preprocessor = ImagePreprocessor()
        with pytest.raises(InvalidImageError, match="empty"):
            preprocessor.preprocess(b"")

    def test_corrupt_bytes_raises_error(self):
        """Verify random corrupted bytes raise an appropriate preprocessor error."""
        preprocessor = ImagePreprocessor()
        corrupt_bytes = b"NotAnImageCorruptedData1234567890"
        with pytest.raises(UnsupportedFormatError):
            preprocessor.preprocess(corrupt_bytes)

    def test_corrupt_jpeg_stream_raises_corrupt_image_error(self):
        """Verify JPEG with valid magic bytes but truncated/mutilated payload raises CorruptImageError."""
        preprocessor = ImagePreprocessor()
        corrupt_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 20
        with pytest.raises(CorruptImageError):
            preprocessor.preprocess(corrupt_jpeg)

    def test_unsupported_formats_rejected(self):
        """Verify formats like GIF and BMP are explicitly rejected with UnsupportedFormatError."""
        preprocessor = ImagePreprocessor()

        # GIF
        gif_bytes = create_synthetic_image("GIF", width=100, height=100)
        with pytest.raises(UnsupportedFormatError) as exc_info:
            preprocessor.preprocess(gif_bytes)
        assert "GIF" in str(exc_info.value)

        # BMP
        bmp_bytes = create_synthetic_image("BMP", width=100, height=100)
        with pytest.raises(UnsupportedFormatError) as exc_info:
            preprocessor.preprocess(bmp_bytes)
        assert "BMP" in str(exc_info.value)

    def test_file_size_limit_enforced_before_decoding(self):
        """Verify size limits are enforced prior to decoding."""
        # Limit to 1 MB for testing
        preprocessor = ImagePreprocessor(max_size_mb=1)
        oversized_bytes = b"x" * (1 * 1024 * 1024 + 100)

        with pytest.raises(OversizedImageError) as exc_info:
            preprocessor.preprocess(oversized_bytes)
        assert exc_info.value.size_bytes > exc_info.value.max_bytes

    def test_exif_orientation_correction(self):
        """Verify mobile camera EXIF orientation tag 6 (270 deg) is corrected."""
        # 400x200 image rotated 90 degrees CW (Tag 6) should transpose to 200x400
        raw_bytes = create_synthetic_image(
            "JPEG",
            width=400,
            height=200,
            exif_orientation=6,
        )
        preprocessor = ImagePreprocessor()
        result = preprocessor.preprocess(raw_bytes)

        # Transposed dimensions should swap width and height
        assert result.processed_dimensions == (200, 400)
        assert result.exif_rotation_applied == 270

    def test_mathematical_stroke_preservation(self):
        """Verify thin strokes (fraction bars, minus signs) remain intact after CLAHE enhancement."""
        raw_bytes = create_synthetic_image(
            "PNG",
            width=300,
            height=200,
            with_math_strokes=True,
        )
        preprocessor = ImagePreprocessor(clahe_clip_limit=1.5)
        result = preprocessor.preprocess(raw_bytes, enhance_contrast=True)

        decoded = Image.open(io.BytesIO(result.processed_bytes))
        assert decoded.size == (300, 200)

        # Ensure thin stroke pixels are still significantly darker than white paper background
        # Fraction bar was drawn at y=50 from x=20 to x=100
        stroke_pixel = decoded.getpixel((60, 50))
        # Stroke must be dark (R, G, B < 100), not erased by contrast enhancement
        assert stroke_pixel[0] < 100 and stroke_pixel[1] < 100 and stroke_pixel[2] < 100

    def test_resizing_downsamples_oversized_dimensions(self):
        """Verify large images above max_dimension are proportionally scaled down."""
        raw_bytes = create_synthetic_image("JPEG", width=3000, height=1500)
        preprocessor = ImagePreprocessor(max_dimension=1500)
        result = preprocessor.preprocess(raw_bytes)

        assert result.was_resized is True
        assert result.processed_dimensions == (1500, 750)

    def test_fallback_availability(self):
        """Verify result holds original bytes and allows retrieval of fallback bytes."""
        raw_bytes = create_synthetic_image("JPEG", width=200, height=100)
        preprocessor = ImagePreprocessor()
        result = preprocessor.preprocess(raw_bytes)

        assert result.get_effective_bytes(use_original=False) == result.processed_bytes
        assert result.get_effective_bytes(use_original=True) == raw_bytes
