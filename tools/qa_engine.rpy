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
        g.start("熊大", "森林运动会", 5, mode="亲子共玩")
        g._qte_result = True
        g.last_qte_success = True
        g.family_discussion = "比较了不同的办法"
        g.turn_count = 1
        g.user_responses = ["A"]
        g.apply_stats({"智": 1})
        restored = StoryGame()
        restored.__setstate__(g.__getstate__())
        assert restored._qte_result is True
        assert restored.last_qte_success is True
        assert restored.family_discussion == g.family_discussion
        assert restored.stats == g.stats
        assert build_local_story(restored) == build_local_story(g)
        results.append({"check": "state restoration preserves route, QTE, family and stats", "passed": True})
        restored._full_response = build_local_story(restored)
        restored.finalize_stream_response()
        count = len(restored.messages)
        restored.finalize_stream_response()
        assert len(restored.messages) == count
        results.append({"check": "response finalization is idempotent", "passed": True})
        global call_ai
        original_call_ai = call_ai
        def stale_result(messages, game_ref, purpose):
            game_ref._request_epoch += 1
            return "stale result"
        try:
            call_ai = stale_result
            g.ai_result = None
            g.parent_report_result = None
            g._eval_messages = []
            g._report_messages = []
            g._bg_call_eval(g._request_epoch)
            g._bg_call_parent_report(g._request_epoch)
            assert g.ai_result is None and g.parent_report_result is None
            results.append({"check": "stale evaluation and report discarded", "passed": True})
        finally:
            call_ai = original_call_ai
        output = os.environ["XCMQY_ENGINE_OUTPUT"]
        with open(output, "w", encoding="utf-8") as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)

testsuite engine_regression:
    testcase deterministic_checks:
        $ run_audit_logic()
    teardown:
        exit
