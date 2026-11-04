"""Image preprocessing service for mathematical documents.

Validates uploaded images, enforces size constraints prior to decoding,
corrects smartphone EXIF orientation, applies conservative contrast enhancement
designed to preserve delicate mathematical symbols (fraction bars, superscripts,
subscripts, minus signs), and retains original image data as a fallback.
"""

import io
from dataclasses import dataclass
from typing import Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings


# Magic byte signatures for early format validation
MAGIC_SIGNATURES = {
    "JPEG": (b"\xff\xd8\xff",),
    "PNG": (b"\x89PNG\r\n\x1a\n",),
    "WEBP": (b"RIFF",),  # RIFF....WEBP checked additionally
}

SUPPORTED_PIL_FORMATS: Set[str] = {"JPEG", "PNG", "WEBP"}
FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class PreprocessorError(Exception):
    """Base exception for all image preprocessing failures."""
    pass


class OversizedImageError(PreprocessorError):
    """Raised when raw image data exceeds the allowed size limit before decoding."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"Image size ({size_bytes / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of "
            f"{max_bytes / (1024 * 1024):.2f} MB."
        )


class UnsupportedFormatError(PreprocessorError):
    """Raised when image format is not among supported types (JPG, JPEG, PNG, WEBP)."""

    def __init__(self, detected_format: str, allowed_formats: Set[str]) -> None:
        self.detected_format = detected_format
        self.allowed_formats = allowed_formats
        super().__init__(
            f"Unsupported image format '{detected_format}'. Allowed formats: "
            f"{', '.join(sorted(allowed_formats))}."
        )


class CorruptImageError(PreprocessorError):
    """Raised when image bytes are corrupt, truncated, or cannot be decoded."""
    pass


class InvalidImageError(PreprocessorError):
    """Raised when image data is fundamentally invalid (empty or degenerate dimensions)."""
    pass


@dataclass(frozen=True)
class PreprocessedImageResult:
    """Container holding preprocessed image output alongside the original for fallback."""

    original_bytes: bytes
    processed_bytes: bytes
    format: str
    mime_type: str
    original_dimensions: Tuple[int, int]  # (width, height)
    processed_dimensions: Tuple[int, int]  # (width, height)
    was_resized: bool
    exif_rotation_applied: int  # 0, 90, 180, 270 degrees
    is_preprocessed: bool

    def get_effective_bytes(self, use_original: bool = False) -> bytes:
        """Return either the processed image bytes or original fallback bytes."""
        return self.original_bytes if use_original else self.processed_bytes


class ImagePreprocessor:
    """Preprocesses camera photographs and scans of mathematical papers."""

    def __init__(
        self,
        max_size_mb: Optional[int] = None,
        max_dimension: int = 2560,
        clahe_clip_limit: float = 1.5,
        clahe_grid_size: Tuple[int, int] = (8, 8),
    ) -> None:
        self.max_bytes = (max_size_mb or settings.MAX_IMAGE_SIZE_MB) * 1024 * 1024
        self.max_dimension = max_dimension
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_grid_size = clahe_grid_size

    def preprocess(
        self,
        raw_bytes: bytes,
        enhance_contrast: bool = True,
    ) -> PreprocessedImageResult:
        """Execute the full preprocessing pipeline on raw image bytes.

        1. Enforces size limits before decoding.
        2. Validates format via magic headers and Pillow verification.
        3. Corrects smartphone EXIF orientation.
        4. Safely composites transparency over white and converts to RGB.
        5. Performs conservative CLAHE contrast enhancement preserving thin math strokes.
        6. Proportionally downsamples if max dimension exceeds threshold.
        7. Returns result container retaining original bytes for fallback.
        """
        # Step 1: Pre-decoding byte size validation
        self._validate_size(raw_bytes)

        # Step 2: Format inspection & safe PIL loading
        pil_image, detected_format = self._inspect_and_load(raw_bytes)
        original_dimensions = (pil_image.width, pil_image.height)

        # Step 3: EXIF orientation correction
        oriented_image, rotation_applied = self._correct_exif_orientation(pil_image)

        # Step 4: Alpha compositing & RGB normalization
        rgb_image = self._normalize_rgb(oriented_image)

        # Step 5: Conservative contrast enhancement preserving fine math symbols
        if enhance_contrast:
            enhanced_image = self._enhance_contrast_conservatively(rgb_image)
        else:
            enhanced_image = rgb_image

        # Step 6: Gentle resizing if dimensions exceed maximum threshold
        final_image, was_resized = self._resize_if_needed(enhanced_image)
        processed_dimensions = (final_image.width, final_image.height)

        # Step 7: Encode processed image into byte stream
        processed_bytes = self._encode_image(final_image, detected_format)

        return PreprocessedImageResult(
            original_bytes=raw_bytes,
            processed_bytes=processed_bytes,
            format=detected_format,
            mime_type=FORMAT_TO_MIME.get(detected_format, "image/jpeg"),
            original_dimensions=original_dimensions,
            processed_dimensions=processed_dimensions,
            was_resized=was_resized,
            exif_rotation_applied=rotation_applied,
            is_preprocessed=enhance_contrast or was_resized or rotation_applied > 0,
        )

    def _validate_size(self, raw_bytes: bytes) -> None:
        """Enforce size limits strictly before allocating decoding buffers."""
        size = len(raw_bytes)
        if size == 0:
            raise InvalidImageError("Image data is empty (0 bytes).")
        if size > self.max_bytes:
            raise OversizedImageError(size_bytes=size, max_bytes=self.max_bytes)

    def _inspect_and_load(self, raw_bytes: bytes) -> Tuple[Image.Image, str]:
        """Validate image magic bytes, detect format, and safely decode."""
        # Fast early-rejection magic byte check
        is_known_magic = False
        if raw_bytes.startswith(MAGIC_SIGNATURES["JPEG"][0]):
            is_known_magic = True
        elif raw_bytes.startswith(MAGIC_SIGNATURES["PNG"][0]):
            is_known_magic = True
        elif raw_bytes.startswith(b"RIFF") and len(raw_bytes) >= 12 and raw_bytes[8:12] == b"WEBP":
            is_known_magic = True

        try:
            pil_image = Image.open(io.BytesIO(raw_bytes))
            detected_format = pil_image.format or ""
        except UnidentifiedImageError as err:
            if is_known_magic:
                raise CorruptImageError(
                    "Image signature matches supported format but stream is corrupted or truncated."
                ) from err
            raise UnsupportedFormatError(
                detected_format="unknown",
                allowed_formats=SUPPORTED_PIL_FORMATS,
            ) from err
        except Exception as err:
            raise CorruptImageError(f"Failed to inspect image headers: {err}") from err

        if detected_format not in SUPPORTED_PIL_FORMATS:
            raise UnsupportedFormatError(
                detected_format=detected_format or "unknown",
                allowed_formats=SUPPORTED_PIL_FORMATS,
            )

        if not is_known_magic and detected_format in SUPPORTED_PIL_FORMATS:
            # File claims supported format but magic bytes mismatch
            raise CorruptImageError(
                f"Image header claims {detected_format} but magic signature is invalid."
            )

        try:
            pil_image.load()
        except Exception as err:
            raise CorruptImageError(f"Image raster stream is corrupt or truncated: {err}") from err

        if pil_image.width <= 0 or pil_image.height <= 0:
            raise InvalidImageError(
                f"Degenerate image dimensions: {pil_image.width}x{pil_image.height}."
            )

        return pil_image, detected_format

    def _correct_exif_orientation(self, img: Image.Image) -> Tuple[Image.Image, int]:
        """Normalize camera orientation according to EXIF metadata."""
        orientation_tag = None
        try:
            exif = img.getexif()
            if exif:
                orientation_tag = exif.get(0x0112)  # EXIF orientation tag ID
        except Exception:
            pass

        rotation_deg = 0
        if orientation_tag == 3:
            rotation_deg = 180
        elif orientation_tag == 6:
            rotation_deg = 270
        elif orientation_tag == 8:
            rotation_deg = 90

        try:
            transposed = ImageOps.exif_transpose(img)
            return (transposed if transposed is not None else img), rotation_deg
        except Exception:
            return img, 0

    def _normalize_rgb(self, img: Image.Image) -> Image.Image:
        """Convert image to RGB, safely compositing transparent alphas over white."""
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img_rgba = img.convert("RGBA")
            # Create a solid white background to prevent dark maths symbols from vanishing
            white_bg = Image.new("RGBA", img_rgba.size, (255, 255, 255, 255))
            composite = Image.alpha_composite(white_bg, img_rgba)
            return composite.convert("RGB")
        if img.mode != "RGB":
            return img.convert("RGB")
        return img

    def _enhance_contrast_conservatively(self, img: Image.Image) -> Image.Image:
        """Apply conservative CLAHE contrast equalization in LAB space.

        Preserves delicate pencil/pen strokes, fraction bars, superscripts,
        subscripts, and decimal points while mitigating uneven page shadows.
        """
        img_np = np.array(img)

        # Convert to LAB space so contrast is applied strictly to luminance (L) channel
        lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Low clip limit (e.g. 1.5) avoids washing out faint strokes or creating noisy halos
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_grid_size,
        )
        enhanced_l = clahe.apply(l_channel)

        merged_lab = cv2.merge([enhanced_l, a_channel, b_channel])
        enhanced_rgb_np = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2RGB)

        return Image.fromarray(enhanced_rgb_np)

    def _resize_if_needed(self, img: Image.Image) -> Tuple[Image.Image, bool]:
        """Proportionally downsample image if any dimension exceeds maximum threshold."""
        width, height = img.size
        max_dim = max(width, height)

        if max_dim <= self.max_dimension:
            return img, False

        scale = self.max_dimension / float(max_dim)
        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))

        # Use Lanczos resampling to preserve fine math stroke details
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return resized, True

    def _encode_image(self, img: Image.Image, output_format: str) -> bytes:
        """Encode PIL Image to bytes using high quality settings."""
        buffer = io.BytesIO()
        if output_format == "JPEG":
            img.save(buffer, format="JPEG", quality=92, optimize=True)
        elif output_format == "PNG":
            img.save(buffer, format="PNG", optimize=True)
        elif output_format == "WEBP":
            img.save(buffer, format="WEBP", quality=92, method=6)
        else:
            img.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()
