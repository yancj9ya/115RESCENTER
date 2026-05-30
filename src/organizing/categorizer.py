from __future__ import annotations

from typing import Final, Iterable, Literal

from .filename_parser import CategoryHint

MediaCategory = Literal["anime", "variety", "documentary", "movie", "tv"]

_DOCUMENTARY_GENRE_IDS: Final[frozenset[int]] = frozenset({99})
_ANIMATION_GENRE_IDS: Final[frozenset[int]] = frozenset({16})
_VARIETY_GENRE_IDS: Final[frozenset[int]] = frozenset({10764, 10767})


def categorize_tmdb_media(
    *,
    kind: str | None,
    genre_ids: Iterable[int] = (),
    title_hint: CategoryHint | None = None,
) -> MediaCategory:
    genres = frozenset(int(value) for value in genre_ids if value is not None)

    if genres & _DOCUMENTARY_GENRE_IDS:
        return "documentary"
    if genres & _ANIMATION_GENRE_IDS:
        return "anime"
    if genres & _VARIETY_GENRE_IDS:
        return "variety"

    if title_hint is not None:
        return title_hint

    if kind == "tv":
        return "tv"
    return "movie"


__all__ = [
    "MediaCategory",
    "categorize_tmdb_media",
]
