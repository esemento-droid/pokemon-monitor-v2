"""Sanitize module — cleans product data before DB insert."""

def sanitize_batch(products):
    """Clean product batch — remove invalid entries, fix encoding."""
    if not products:
        return products
    cleaned = []
    for p in products:
        if not p.get("id") or not p.get("name"):
            continue
        # Fix encoding issues
        name = p.get("name", "")
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="ignore")
        p["name"] = name.strip()
        cleaned.append(p)
    return cleaned
