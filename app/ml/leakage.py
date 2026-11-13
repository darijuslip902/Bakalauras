"""Artimų dublikatų paieška tarp mokymo ir testavimo tekstų (apsauga nuo nutekėjimo).

Tikslūs dublikatai pašalinami pagal tekstų santrauką (`text_fingerprint`). Čia ieškoma beveik
vienodų tekstų (pvz. tas pats šablonas, tas pats stack trace su kitu skaičiumi): kosinuso
panašumas tarp žodžių maišų. Naudojamas `HashingVectorizer` – jis neturi žodyno ir nieko
„neišmoksta“ iš žymų ar testo duomenų, todėl negali įnešti nutekėjimo į modelio požymius.
"""

from collections.abc import Sequence

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

DEFAULT_THRESHOLD = 0.9
_CHUNK = 500


def near_duplicate_indices(
    candidates: Sequence[str], references: Sequence[str], threshold: float = DEFAULT_THRESHOLD
) -> list[int]:
    """`candidates` indeksai, kurių kosinuso panašumas bent su vienu `references` tekstu ≥ threshold."""
    if not candidates or not references:
        return []
    vectorizer = HashingVectorizer(
        n_features=2**20, alternate_sign=False, norm="l2", lowercase=True,
        token_pattern=r"(?u)\b\w\w+\b",
    )
    reference_matrix = vectorizer.transform(references).T.tocsr()
    found: list[int] = []
    for start in range(0, len(candidates), _CHUNK):
        chunk = vectorizer.transform(candidates[start:start + _CHUNK])
        best = (chunk @ reference_matrix).max(axis=1).toarray().ravel()
        found += [start + int(i) for i in np.nonzero(best >= threshold)[0]]
    return found
