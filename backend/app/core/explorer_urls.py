"""Lora (AlgoKit) transaction URLs for API responses (NETWORK-aware)."""

from __future__ import annotations

import os
from urllib.parse import quote

_NETWORK = (os.getenv("NETWORK") or "testnet").strip().lower()
if _NETWORK == "mainnet":
    _LORA_EXPLORER_BASE = "https://lora.algokit.io/mainnet"
else:
    _LORA_EXPLORER_BASE = "https://lora.algokit.io/testnet"


def lora_transaction_explorer_url(tx_id: str | None) -> str | None:
    """Return Lora explorer URL for ``tx_id``, or ``None`` if missing/blank."""
    if tx_id is None:
        return None
    tid = str(tx_id).strip()
    if not tid:
        return None
    return f"{_LORA_EXPLORER_BASE}/transaction/{quote(tid)}"
