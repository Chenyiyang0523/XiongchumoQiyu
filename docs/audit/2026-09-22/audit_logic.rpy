init 999 python:
    def run_audit_logic():
        import io
        import json
        import os
        from types import SimpleNamespace

        results = []
        cases = 0
        for character in CHARACTERS:
            for duration in (5, 10, 15, 20):
                for difficulty in ("儿童难度", "青少年难度"):
                    for letter in ("A", "B", "C"):
                        g = StoryGame()
                        opening = g.start(character, "测试情景", duration, difficulty=difficulty)
                        assert len(extract_options(opening)) == 3
                        for turn in range(g.max_turns):
                            response, ended = g.continue_story(letter)
                            for seg in parse_ai_response(response):
                                if seg[0] == "stats":
                                    g.apply_stats(seg[1])
                            assert ended == (turn + 1 == g.max_turns)
                            assert all(0 <= value <= 10 for value in g.stats.values())
                            if not ended:
                                assert len(extract_options(response)) == 3
                        assert "【剧终】" in response
                        assert extract_score_from_eval(build_local_evaluation(g)) == _local_score(g)
                        assert len(g.user_responses) == g.max_turns
                        cases += 1
        results.append({"check": "offline model matrix (no GUI)", "passed": True, "cases": cases})

        global AI_ENDPOINT, AI_API_KEY, _story_urlopen
        original = (AI_ENDPOINT, AI_API_KEY, _story_urlopen)
        AI_API_KEY = ""
        try:
            for endpoint, accepted in (("http://example.invalid/api", False), ("http://127.0.0.1/api", True), ("https://example.invalid/api", True), ("", False)):
                AI_ENDPOINT = endpoint
                assert bool(_validated_ai_endpoint()) == accepted
            results.append({"check": "endpoint validation", "passed": True, "cases": 4})
            AI_ENDPOINT = "http://127.0.0.1/audit"
            base = StoryGame()
            base.start("熊大", "测试", 5)
            expected = build_local_story(base)
            def raise_timeout(*args, **kwargs):
                raise TimeoutError("synthetic timeout")
            def raise_connection(*args, **kwargs):
                raise ConnectionError("synthetic connection failure")
            transports = [
                ("connection failure", raise_connection),
                ("timeout", raise_timeout),
                ("empty SSE", lambda *a, **k: io.BytesIO(b"data: [DONE]\n")),
                ("malformed SSE JSON", lambda *a, **k: io.BytesIO(b"data: {bad}\n\ndata: [DONE]\n")),
                ("incomplete SSE", lambda *a, **k: io.BytesIO(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')),
                ("oversize SSE", lambda *a, **k: io.BytesIO(b"data: " + b"x" * (AI_MAX_RESPONSE_BYTES + 1))),
            ]
            for name, transport in transports:
                g = StoryGame()
                g.start("熊大", "测试", 5)
                g.online_enabled = True
                _story_urlopen = transport
                epoch = g._reset_stream_state()
                call_ai_stream([], g, epoch)
                assert g._full_response == expected
                assert len(g._segment_queue) > 0
                results.append({"check": "mock transport fallback: " + name, "passed": True})
            g = StoryGame()
            assert not _commit_story_response(g, "stale text", g._request_epoch - 1)
            assert not g._full_response and not g._segment_queue
            results.append({"check": "stale story commit rejected", "passed": True})
        finally:
            AI_ENDPOINT, AI_API_KEY, _story_urlopen = original

        g = StoryGame()
        g.start("熊大", "森林运动会", 10)
        g.turn_count = 1
        g.user_responses = ["A"]
        reference = build_local_story(g)
        variants = []
        for attribute, value in (("scenario", "海底寻找宝藏"), ("_game_mode", "亲子共玩"), ("_game_difficulty", "青少年难度"), ("powerup", "问题提示神器"), ("fate_text", "变成宇航员")):
            old = getattr(g, attribute)
            setattr(g, attribute, value)
            variants.append({"setting": attribute, "changes_middle_chapter": build_local_story(g) != reference})
            setattr(g, attribute, old)
        results.append({"check": "setting behavior probe", "observed": variants})
        g.ending_type = "留白式结局"
        g.turn_count = g.max_turns
        results.append({"check": "chosen ending consistency", "story_is_open_ended": "下一次冒险" in build_local_story(g), "record_type": extract_ending_info(build_local_evaluation(g)).get("ending_type")})
        output = os.environ["XCMQY_AUDIT_OUTPUT"]
        with open(output, "w", encoding="utf-8") as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)

testsuite audit_logic:
    testcase deterministic_checks:
        $ run_audit_logic()
    teardown:
        exit
