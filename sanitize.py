"""Centralna walidacja i normalizacja produktów przed zapisem."""


def sanitize_product(p: dict) -> dict:
    """Normalizuje typy pól produktu dla SQLite."""
    # ID musi być stringiem
    p["id"] = str(p.get("id", ""))

    # image - lista -> pierwszy element
    img = p.get("image", "")
    if isinstance(img, list):
        p["image"] = img[0] if img else ""
    elif not isinstance(img, str):
        p["image"] = str(img) if img else ""

    # stock - lista -> None, inne typy OK
    stock = p.get("stock")
    if isinstance(stock, list):
        p["stock"] = stock[0] if stock else None

    # price - number -> string
    price = p.get("price")
    if isinstance(price, (int, float)):
        p["price"] = f"{price} zł"
    elif price is None:
        p["price"] = "brak"

    # available - upewnij się ze bool
    p["available"] = bool(p.get("available", False))

    # name - upewnij się ze string
    p["name"] = str(p.get("name", ""))

    # url - upewnij się ze string
    p["url"] = str(p.get("url", ""))

    # shop - wymagane
    p["shop"] = str(p.get("shop", "unknown"))

    return p


def sanitize_batch(products: list) -> list:
    """Waliduj i normalizuj listę produktów."""
    result = []
    for p in products:
        if not p.get("id"):
            continue
        result.append(sanitize_product(p))
    return result
