from __future__ import annotations

from pathlib import Path

from PIL import Image


def average_hash_hex(image_path: Path, hash_size: int = 8) -> str:
    """Perceptual average hash as hex string (default 64-bit)."""
    img = Image.open(image_path).convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, value in enumerate(pixels):
        if value >= avg:
            bits |= 1 << i
    width = (hash_size * hash_size + 3) // 4
    return f"{bits:0{width}x}"


def hash_similarity(hash_a: str, hash_b: str) -> float:
    """Similarity in [0, 1] from Hamming distance of equal-length hex hashes."""
    if not hash_a or not hash_b:
        return 0.0
    try:
        a = int(hash_a, 16)
        b = int(hash_b, 16)
    except ValueError:
        return 0.0
    bits = max(len(hash_a), len(hash_b)) * 4
    if bits <= 0:
        return 0.0
    xor = a ^ b
    distance = xor.bit_count() if hasattr(int, "bit_count") else bin(xor).count("1")
    return max(0.0, 1.0 - distance / bits)
