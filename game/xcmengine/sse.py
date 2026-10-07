"""Server-sent-events reading and OpenAI-style chat chunk parsing (stdlib only)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass
class Delta:
    content: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    usage: dict | None = None


def iter_sse_data(readline: Callable[[], bytes]) -> Iterator[str]:
    data_lines: list[str] = []
    while True:
        raw = readline()
        if not raw:
            break
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                if payload.strip() == "[DONE]":
                    return
                yield payload
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
    if data_lines:
        payload = "\n".join(data_lines)
        if payload.strip() != "[DONE]":
            yield payload


def parse_chunk(payload: str) -> Delta:
    obj = json.loads(payload)
    d = Delta(usage=obj.get("usage"))
    choices = obj.get("choices") or []
    if choices:
        ch = choices[0] or {}
        delta = ch.get("delta") or {}
        d.content = delta.get("content") or ""
        d.reasoning = delta.get("reasoning_content") or ""
        d.finish_reason = ch.get("finish_reason")
    return d
