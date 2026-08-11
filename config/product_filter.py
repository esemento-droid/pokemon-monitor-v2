"""
Centralny filtr produktów — jedna lista EXCLUDE dla WSZYSTKICH scraperów.

Użycie w scraperze:
    from config.product_filter import should_exclude

    if should_exclude(product_name):
        continue  # skip this product

Lista jest ładowana z config/product_filter.json.
Plik JSON jest RELOADOWANY co wywołanie (hot-reload bez restartu).
Dodajesz słowo w JSON → natychmiast działa wszędzie.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

FILTER_PATH = Path(__file__).parent / "product_filter.json"

_cached_keywords: Optional[List[str]] = None
_cached_mtime: float = 0


def _load_filter() -> List[str]:
    """Load and flatten all exclude lists from JSON. Hot-reload on file change."""
    global _cached_keywords, _cached_mtime

    try:
        mtime = os.path.getmtime(FILTER_PATH)
    except OSError:
        mtime = 0

    # Return cache if file hasn't changed
    if _cached_keywords is not None and mtime == _cached_mtime:
        return _cached_keywords

    try:
        data = json.loads(FILTER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"[FILTER] Failed to load {FILTER_PATH}: {e}")
        if _cached_keywords is not None:
            return _cached_keywords  # Use stale cache
        return []

    # Flatten all exclude_* lists
    keywords = []
    for key, value in data.items():
        if key.startswith("exclude_") and isinstance(value, list):
            keywords.extend(value)

    # Normalize: lowercase, strip
    keywords = [kw.lower().strip() for kw in keywords if kw.strip()]

    _cached_keywords = keywords
    _cached_mtime = mtime

    logger.info(f"[FILTER] Loaded {len(keywords)} exclude keywords from {FILTER_PATH}")
    return keywords


def should_exclude(product_name: str) -> bool:
    """
    Returns True if product should be EXCLUDED (it's junk).
    Returns False if product should PASS (it's a valid sealed product).

    Usage:
        if should_exclude("100 Ultra Pro Soft Sleeves"):
            continue  # skip
    """
    if not product_name:
        return True

    keywords = _load_filter()
    name_lower = product_name.lower()

    return any(kw in name_lower for kw in keywords)


def get_exclude_keywords() -> List[str]:
    """Get raw list of exclude keywords (for scrapers that need the list directly)."""
    return _load_filter()
