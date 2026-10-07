"""Engine settings and API-key resolution. Pure Python; never imports renpy."""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROLES = ("bible", "chapter", "repair", "gate", "idea", "judge")

DEFAULTS: dict[str, Any] = {
    "api_base": "https://open.bigmodel.cn/api/paas/v4",
    "use_system_proxy": False,
    "models": {"bible": "glm-4.7", "chapter": "glm-4.7", "repair": "glm-4.7",
               "gate": "glm-4.7-flashx", "idea": "glm-4.7-flashx", "judge": "glm-5.3"},
    # the writer's model once a chapter's streams failed twice, and for the secret's last try ("" turns it off)
    "fallback_model": "glm-4.7-flashx",
    # lean: one call per chapter in the baseline's words, cut after its fork (M3 r3); classic: the r2 pipeline
    # (director briefs, setups and secret, repairs, structural rewrites), kept for comparison until round 3 is passed
    "writer": {"mode": "lean"},
    # thinking per model: "disabled" where the API allows it, else a reasoning_effort level
    "thinking": {"glm-4.7": "disabled", "glm-4.7-flashx": "disabled", "glm-5-turbo": "disabled",
                 "glm-5.1": "disabled", "glm-5.3": "low", "glm-5.3-flash": "low"},
    "judge_thinking": "high",
    "temperature": {"bible": 0.9, "chapter": 0.9, "repair": 0.5, "gate": 0.2, "idea": 0.2, "judge": 0.2},
    "max_tokens": {"bible": 5000, "chapter": 3000, "repair": 1200, "gate": 600, "idea": 500, "judge": 4000},
    "top_p": 0.95,
    "timeouts": {"connect": 10.0, "idle": 30.0, "total": 120.0, "total_bible": 180.0},
    "retries": 3,
    "image": {"page_model": "cogview-4-250304", "cover_model": "cogview-4-250304", "quality": "standard",
              "size": "1344x768", "timeout": 90.0, "concurrency": 3},
    "tts": {"model": "glm-tts", "narrator": "tongtong", "speed": 1.0, "concurrency": 2,
            "voices": {"xionger": "jam", "jiji": "kazi", "qiang": "xiaochen", "xiongda": "chuichui"},
            "fallback_say_voice": "Tingting"},
    "concurrency": {"text": 3},
    "speculate_text": True,
    "prefetch_images": True,
    "illustration_mode": "page",
    "narration": True,
    "character_voices": False,
    "length": "medium",
}


@dataclass(frozen=True)
class RoleConfig:
    model: str
    temperature: float
    max_tokens: int
    thinking: str
    top_p: float


def _merge(dst: dict, src: Mapping) -> None:
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)


class Settings:
    def __init__(self, overrides: Mapping | None = None, env: Mapping | None = None):
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        if overrides:
            _merge(self.data, overrides)
        self._env = os.environ if env is None else env

    def get(self, path: str, default: Any = None) -> Any:
        cur: Any = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def role(self, role: str) -> RoleConfig:
        if role not in ROLES:
            raise KeyError(role)
        model = self.data["models"][role]
        thinking = self.data["thinking"].get(model, "low")
        if role == "judge" and thinking != "disabled":
            thinking = self.data.get("judge_thinking", "high")
        return RoleConfig(model=model, temperature=float(self.data["temperature"][role]),
                          max_tokens=int(self.data["max_tokens"][role]), thinking=thinking,
                          top_p=float(self.data["top_p"]))

    @property
    def api_base(self) -> str:
        return (self._env.get("XCMQY_API_BASE") or self.data["api_base"]).strip().rstrip("/")

    def to_dict(self) -> dict:
        return copy.deepcopy(self.data)


def resolve_api_key(env: Mapping | None = None, home: str | Path | None = None) -> str | None:
    env = os.environ if env is None else env
    key = (env.get("XCMQY_API_KEY") or "").strip()
    if key:
        return key
    path = Path(home if home is not None else Path.home()) / ".xcmqy" / "config.json"
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    key = str(data.get("api_key", "")).strip() if isinstance(data, dict) else ""
    return key or None
