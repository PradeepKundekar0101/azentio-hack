"""Perceptual hash (DCT pHash) of a page image, so a re-scanned or re-saved copy of the same bill is recognised even
though its bytes and SHA-256 differ."""

import numpy as np
from PIL import Image
from scipy.fft import dctn

SIZE = 32  # the image is reduced to 32 x 32 greyscale
LOW = 8  # and the top-left 8 x 8 DCT coefficients (lowest frequencies) give a 64-bit hash


def phash(image: Image.Image) -> str:
    """64-bit perceptual hash as 16 hex digits."""
    small = image.convert("L").resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    coefficients = dctn(np.asarray(small, dtype=np.float64), norm="ortho")[:LOW, :LOW]
    median = np.median(coefficients.flatten()[1:])  # the DC term would dominate the median
    bits = (coefficients > median).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def phash_distance(a: str, b: str) -> int:
    """Hamming distance between two hashes: 0 for the same image, up to 64."""
    return (int(a, 16) ^ int(b, 16)).bit_count()
