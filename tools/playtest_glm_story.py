#!/usr/bin/env python3
"""Opt-in paid smoke test through the actual launcher bridge and game story path."""
import argparse
import json
from pathlib import Path
import secrets
import threading
import time

from run_glm_game import GLM, ThreadingHTTPServer, handler_for
from test_online_story import load_story

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/integration/2026-10-07/linux-live-stories.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow metered BigModel requests")
    parser.add_argument("--only-shadow", action="store_true", help="Recheck the custom-input story only")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to authorize metered API calls")
    provider = GLM()
    usage, validation = [], []
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(provider, token))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    result = {"writer": "Linux LeanWriter m3-r2@8514075", "model": "glm-4.7", "endpoint": "BigModel ordinary metered API", "stories": [], "usage": usage, "validation": validation}
    output = OUTPUT.with_name("linux-live-shadow.json") if args.only_shadow else OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        ns = load_story()
        ns["renpy"].log = lambda message: validation.append(message)
        ns["AI_ENDPOINT"] = "http://127.0.0.1:%d/v1/chat/completions" % server.server_port
        ns["AI_API_KEY"] = token
        original_factory = ns["linux_story_client"]
        def metered_client():
            client = original_factory()
            complete = client.complete
            def recorded(*args, **kwargs):
                old_meter = kwargs.get("meter")
                def meter(model, tokens, estimated):
                    usage.append(dict(tokens, model=model, estimated=estimated))
                    if old_meter:
                        old_meter(model, tokens, estimated)
                kwargs["meter"] = meter
                return complete(*args, **kwargs)
            client.complete = recorded
            return client
        ns["linux_story_client"] = metered_client
        cards = ns["_linux_story"].load_content().seeds["cards"]
        for index, duration in (((1, 5),) if args.only_shadow else ((0, 10), (1, 5))):
            g = ns["StoryGame"]()
            entry = {"scenario": cards[index]["hook"], "duration": duration, "turns": []}
            result["stories"].append(entry)
            began = time.monotonic()
            g.start_stream("熊二" if index == 0 else "熊大", entry["scenario"], duration, online_enabled=True)
            for turn in range(g.max_turns + 1):
                if g.ai_error:
                    entry["error"] = g.ai_error
                    print(json.dumps(validation, ensure_ascii=False), flush=True)
                    raise RuntimeError("Story response failed validation at turn %d" % turn)
                g.finalize_stream_response()
                options = ns["story_options"](g)
                entry["turns"].append({"turn": turn, "seconds": round(time.monotonic() - began, 2),
                    "choice": g.user_responses[-1] if g.user_responses else None,
                    "story": g._full_response, "ended": g.ended})
                print(json.dumps({"story": index + 1, "turn": turn, "seconds": entry["turns"][-1]["seconds"],
                                  "characters": len(g._full_response), "ended": g.ended}, ensure_ascii=False), flush=True)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                while g.has_pending_segments():
                    segment = g.pop_segment()
                    if segment[0] == "stats":
                        g.apply_stats(segment[1])
                if turn == g.max_turns:
                    assert g.ended and not options
                    break
                assert len(options) >= 2 and not g.ended
                if index == 1 and turn == 1:
                    choice = "我想和自己的影子交换工作一天，先问它最想做什么"
                else:
                    letter, text = options[(turn + index) % len(options)]
                    choice = letter + ". " + text
                began = time.monotonic()
                g.continue_story_stream(choice)
            entry["completed"] = True
            entry["linux_state"] = g._linux_state
        result["passed"] = True
    finally:
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        server.shutdown()
        server.server_close()
    print("Saved live story evidence: " + str(output), flush=True)


if __name__ == "__main__":
    main()
