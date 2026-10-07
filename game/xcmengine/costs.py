"""Prices and a running cost ledger (元)."""
from __future__ import annotations

from typing import Callable

PRICES: dict[str, tuple[float, float, float]] = {   # 元 per million tokens: input, output, cached input
    "glm-4.7": (3.0, 14.0, 0.6), "glm-4.7-flashx": (0.5, 3.0, 0.1), "glm-4.7-flash": (0.0, 0.0, 0.0),
    "glm-5.3": (8.0, 28.0, 2.0), "glm-5.3-flash": (0.8, 2.8, 0.23), "glm-5-turbo": (5.0, 22.0, 1.2),
    "glm-5.1": (6.0, 24.0, 1.3),
}
IMAGE_PRICE = {"cogview-4-250304": 0.06, "cogview-4": 0.06, "cogview-3-flash": 0.0, "glm-image": 0.1}
TTS_PRICE_PER_CHAR = 0.0002


def cost_yuan(model: str, usage: dict) -> float:
    p_in, p_out, p_cache = PRICES.get(model, PRICES["glm-5.3"])
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    out = int(usage.get("completion_tokens", 0) or 0)
    cached = int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
    return round(((prompt - cached) * p_in + cached * p_cache + out * p_out) / 1_000_000, 6)


class Ledger:
    def __init__(self) -> None:
        self.yuan = 0.0
        self.calls = 0
        self.images = 0
        self.tts_chars = 0
        self.tokens = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "reasoning_tokens": 0}
        self.estimated = 0          # calls billed from an estimate (the stream ended without its usage chunk)
        self.on_add: Callable[[], None] | None = None     # called after every bill, e.g. to save the spend to disk

    def _billed(self) -> None:
        if self.on_add is not None:
            try:
                self.on_add()
            except OSError:         # saving the spend must never turn a billed call into a failure
                pass

    def add(self, model: str, usage: dict, estimated: bool = False) -> float:
        """Bill one call; the signature doubles as ChatClient.complete's meter(model, usage, estimated)."""
        usage = usage or {}
        c = cost_yuan(model, usage)
        self.yuan += c
        self.calls += 1
        self.estimated += 1 if estimated else 0
        self.tokens["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        self.tokens["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        self.tokens["cached_tokens"] += int(((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
        self.tokens["reasoning_tokens"] += int(((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)) or 0)
        self._billed()
        return c

    def add_image(self, model: str) -> float:
        c = IMAGE_PRICE.get(model, 0.1)
        self.yuan += c
        self.images += 1
        self._billed()
        return c

    def add_tts(self, chars: int) -> float:
        c = chars * TTS_PRICE_PER_CHAR
        self.yuan += c
        self.tts_chars += chars
        self._billed()
        return c

    def to_dict(self) -> dict:
        return {"yuan": round(self.yuan, 6), "calls": self.calls, "estimated": self.estimated, "images": self.images,
                "tts_chars": self.tts_chars, "tokens": dict(self.tokens)}
