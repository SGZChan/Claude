"""Tiny dependency-free text embeddings (feature hashing) + cosine search."""
from __future__ import annotations

import re

import numpy as np

DIM = 1024
_WORD = re.compile(r"[a-z0-9]+")


def embed(text: str) -> np.ndarray:
    words = _WORD.findall(text.lower())
    feats = [(w, 1.0) for w in words] + [(f"{a}_{b}", 1.0) for a, b in zip(words, words[1:])]
    # character trigrams give cheap fuzzy matching (private ~ privacy, invoice ~ invoices)
    feats += [(f"#{w[i:i + 3]}", 0.35) for w in words if len(w) >= 4 for i in range(len(w) - 2)]
    feats += [(f"~{w[:5]}", 0.7) for w in words if len(w) >= 6]  # crude stem: privacy ~ private
    v = np.zeros(DIM, dtype=np.float32)
    for f, wt in feats:
        h = hash_str(f)
        v[h % DIM] += wt if (h >> 20) & 1 else -wt
    n = np.linalg.norm(v)
    return v / n if n else v


def hash_str(s: str) -> int:
    # stable across processes (Python's hash() is salted)
    h = 2166136261
    for ch in s.encode():
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h


def to_blob(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
