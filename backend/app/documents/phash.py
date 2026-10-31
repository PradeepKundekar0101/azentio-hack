"""Perceptual hash (DCT pHash) of a page image, so a re-scanned or re-saved copy of the same bill is recognised even
though its bytes and SHA-256 differ.

The classic 64-bit pHash (32 x 32 pixels, 8 x 8 coefficients) only sees a text page's layout: two different invoices
printed on one template hash 0-4 bits apart. A 256-bit hash (64 x 64 pixels, 16 x 16 coefficients) keeps enough of
the text to tell them apart (26+ bits on the sample scans) while a re-scan stays within a few bits.
"""

import numpy as np
from PIL import Image
from scipy.fft import dctn

SIZE = 64  # the image is reduced to 64 x 64 greyscale
LOW = 16  # and the top-left 16 x 16 DCT coefficients (lowest frequencies) give a 256-bit hash
NEAR_IDENTICAL_DISTANCE = 16  # at most this many differing bits: the same page (the plan's 5 of 64, scaled)


def phash(image: Image.Image) -> str:
    """256-bit perceptual hash as 64 hex digits."""
    small = image.convert("L").resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    coefficients = dctn(np.asarray(small, dtype=np.float64), norm="ortho")[:LOW, :LOW].flatten()
    median = np.median(coefficients[1:])  # the DC term would dominate the median
    bits = "".join("1" if c > median else "0" for c in coefficients)
    return f"{int(bits, 2):064x}"


def phash_distance(a: str, b: str) -> int:
    """Hamming distance between two hashes: 0 for the same image, up to 256."""
    return (int(a, 16) ^ int(b, 16)).bit_count()
