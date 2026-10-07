# 只复制到隔离验收工程；以可控传输跑正式界面和错误重试路径。
init 999 python:
    qa_story_attempts = {}

    def qa_story_client():
        import json as qa_json
        from xcmengine.config import Settings
        from xcmengine.llm import ChatClient, FakeTransport
        with renpy.file("qa_linux_fixture.json") as f:
            fixture = qa_json.loads(f.read())
        turn = game.turn_count
        qa_story_attempts[turn] = qa_story_attempts.get(turn, 0) + 1
        if turn in (0, game.max_turns) and qa_story_attempts[turn] == 1:
            script = [("http", 401, "{}")] * 2
        else:
            objects = ([fixture["head"]] if turn == 0 else []) + [x for ch in fixture["chapters"][turn:] for x in ch]
            text = "\n".join(qa_json.dumps(x, ensure_ascii=False) for x in objects) + "\n"
            chunks = ["data: " + qa_json.dumps({"choices": [{"delta": {"content": text[i:i+7]}}]}, ensure_ascii=False)
                      for i in range(0, len(text), 7)]
            script = [("ok", "\n\n".join(chunks) + "\n\ndata: [DONE]\n\n")]
        return ChatClient(Settings({"retries": 0}, env={}), transport=FakeTransport(script), api_key="test-only", sleep=lambda _: None)

    def qa_story_evaluation(messages, stream=False):
        return build_local_evaluation(game)

label qa_cloud_story:
    scene bg forest
    $ selected_character = "熊二"
    $ story_scenario = _linux_story.load_content().card("c34")["hook"]
    $ story_duration = 10
    $ story_mode = "小朋友独立体验"
    $ story_difficulty = "儿童难度"
    $ story_powerup = ""
    $ story_fate_text = ""
    $ story_ending_type = ""
    $ story_online_enabled = True
    jump story_begin

testsuite story_integration:
    setup:
        $ _test.timeout = 20.0
        $ _test.transition_timeout = 0.1
        $ _preferences.text_cps = 0
        $ _test.screenshot_directory = __import__("os").environ["XCMQY_QA_OUTPUT"]
        $ persistent.accounts = {"user_0": _make_empty_account_data("故事验收", slot_index=0)}
        $ persistent.account_order = ["user_0"]
        $ persistent.current_user = "user_0"
        $ game = StoryGame()
        $ AI_ENDPOINT = "http://127.0.0.1/controlled-test"
        $ _online_request = qa_story_evaluation
        $ linux_story_client = qa_story_client

    testcase retry_and_finish:
        run Start("qa_cloud_story")
        pause until screen "ai_error_screen"
        pause 0.5
        $ qa_original_id = game.run_id
        assert eval (game.turn_count == 0 and not game.ended)
        screenshot "cloud-retry.png"
        click "重试"
        advance until screen "story_choice"
        pause 0.3
        assert eval (game.run_id == qa_original_id and qa_story_attempts[0] == 2)
        screenshot "cloud-choice.png"
        run FileSave(1, page="1", confirm=False)
        assert eval (renpy.can_load("1-1"))
        click "B."
        advance until screen "story_choice"
        assert eval (game.turn_count == 1)
        assert eval ("光头强" in game.user_responses[-1])
        click "C."
        advance until screen "story_choice"
        assert eval (game.turn_count == 2)
        click "A."
        pause until screen "ai_error_screen"
        pause 0.3
        assert eval (game.turn_count == 3 and not game.ended)
        $ qa_before_retry = list(game.messages)
        click "重试"
        advance until screen "badge_unlock_popup"
        click "太棒了！"
        pause until screen "evaluation_screen"
        assert eval (game.ended and game.turn_count == 3)
        assert eval (len(game.user_responses) == 3)
        assert eval (game.messages[:-1] == qa_before_retry)
        assert eval (get_play_stats()["total_plays"] == 1)
        screenshot "cloud-ending.png"

    teardown:
        exit
