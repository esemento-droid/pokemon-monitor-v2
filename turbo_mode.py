"""
Cross-Shop Turbo Mode — when one shop restocks, all related shops go into turbo polling.

Logic:
  - Pokemon TCG drops tend to happen across multiple shops within minutes
  - If shop A restocks a 30th product → shops B, C, D should poll every 1-3s for 5 min
  - After 5 min turbo expires → back to normal polling

Integration in detector.py:
    from turbo_mode import trigger_turbo, is_turbo_active, get_turbo_interval

    # On restock:
    if is_30th_product(product):
        trigger_turbo(shop_name)

    # In scan loop:
    if is_turbo_active():
        delay = get_turbo_interval()  # 1-3s instead of 5-15s
    else:
        delay = normal_delay

State is stored in a JSON file (shared across processes via filesystem).
"""
import json
import time
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("turbo_mode")

BASE_DIR = Path("/opt/pokemon-monitor-v2")
TURBO_STATE_FILE = BASE_DIR / "data" / "turbo_state.json"
TURBO_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# Config
TURBO_DURATION = 300  # 5 minutes of turbo mode
TURBO_INTERVAL = 2  # Poll every 2s during turbo
TURBO_KEYWORDS = ["30", "celebr", "first partner", "anniversary", "rocznica"]

# Shop groups — if one triggers, others go turbo
SHOP_GROUPS = {
    "pokemon_30th": [
        "tcgumisia", "kartexpol", "strefatcg", "japancollectibles",
        "tantis", "smyk", "empik",
    ],
}


def _load_state() -> dict:
    if TURBO_STATE_FILE.exists():
        try:
            return json.loads(TURBO_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    state["updated_at"] = time.time()
    TURBO_STATE_FILE.write_text(json.dumps(state, indent=2))


def trigger_turbo(shop_name: str, product_name: str = "", reason: str = "restock"):
    """
    Activate turbo mode. Called when a significant restock is detected.
    All shops in the same group will poll faster.
    """
    state = _load_state()
    state["active"] = True
    state["triggered_by"] = shop_name
    state["triggered_at"] = time.time()
    state["expires_at"] = time.time() + TURBO_DURATION
    state["reason"] = reason
    state["product"] = product_name
    _save_state(state)
    log.info(f"🚀 TURBO MODE ACTIVATED by {shop_name}: {reason} ({product_name})")


def is_turbo_active() -> bool:
    """Check if turbo mode is currently active."""
    state = _load_state()
    if not state.get("active"):
        return False
    if time.time() > state.get("expires_at", 0):
        # Expired — deactivate
        state["active"] = False
        _save_state(state)
        return False
    return True


def get_turbo_interval() -> float:
    """Get polling interval during turbo mode (seconds)."""
    if is_turbo_active():
        return TURBO_INTERVAL
    return None  # Use normal interval


def get_turbo_shops() -> list:
    """Get list of shops that should be in turbo mode."""
    state = _load_state()
    if not state.get("active"):
        return []
    triggered_by = state.get("triggered_by", "")
    # Find which group this shop belongs to
    for group_name, shops in SHOP_GROUPS.items():
        if triggered_by in shops:
            return shops
    return []


def should_trigger_turbo(product: dict) -> bool:
    """Check if a product restock should activate turbo mode."""
    name = product.get("name", "").lower()
    return any(kw in name for kw in TURBO_KEYWORDS)


def get_turbo_status() -> Optional[dict]:
    """Get current turbo mode status (for logging/Discord)."""
    state = _load_state()
    if not state.get("active"):
        return None
    remaining = state.get("expires_at", 0) - time.time()
    if remaining <= 0:
        return None
    return {
        "active": True,
        "triggered_by": state.get("triggered_by"),
        "product": state.get("product"),
        "remaining_seconds": int(remaining),
        "reason": state.get("reason"),
    }


# === CLI ===
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "trigger":
        shop = sys.argv[2] if len(sys.argv) > 2 else "test"
        trigger_turbo(shop, "Manual test trigger")
        print(f"Turbo triggered by {shop}")
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        status = get_turbo_status()
        if status:
            print(f"🚀 TURBO ACTIVE: triggered by {status['triggered_by']}, "
                  f"{status['remaining_seconds']}s remaining")
        else:
            print("Turbo: inactive")
    else:
        print("Usage: turbo_mode.py [trigger <shop>|status]")
