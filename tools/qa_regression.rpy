# 仅注入隔离测试工程；不进入发行包。
label qa_story:
    $ selected_character = "熊大"
    $ story_scenario = "吉吉国王的森林运动会"
    $ story_duration = 5
    $ story_mode = "亲子共玩"
    $ story_difficulty = "青少年难度"
    $ story_powerup = "问题提示神器"
    $ story_fate_text = ""
    $ story_ending_type = ""
    $ story_online_enabled = False
    jump story_begin

label qa_timeout:
    call screen qte_screen(description="倒计时与失败恢复回归", seconds=3)
    $ qa_qte_result = _return
    "挑战已返回"
    return

testsuite regression:
    setup:
        $ _test.timeout = 15.0
        $ _test.transition_timeout = 0.1
        $ _preferences.text_cps = 0
        $ _test.screenshot_directory = __import__("os").environ["XCMQY_QA_OUTPUT"]
        $ persistent.accounts = {"user_0": _make_empty_account_data("回归测试", slot_index=0)}
        $ persistent.account_order = ["user_0"]
        $ persistent.current_user = "user_0"
        $ game = StoryGame()

    before testcase:
        if not screen "main_menu":
            run MainMenu(confirm=False)
        pause until screen "main_menu"

    testcase full_adventure:
        run Start("qa_story")
        advance until screen "story_choice"
        pause 0.3
        assert eval (game.powerup == "问题提示神器")
        screenshot "choice-hint.png"
        assert eval (renpy.get_widget("story_choice", "local_hint") is not None)
        click "A."
        advance until screen "qte_screen"
        click "轻松完成"
        pause until screen "qte_result_screen"
        click "继续冒险"
        advance until screen "stats_change_popup"
        pause 3.0
        assert "知道了"
        screenshot "popup-after-three-seconds.png"
        click "知道了"
        pause until screen "family_discussion"
        screenshot "family-discussion.png"
        click "我们比较了另一种办法"
        pause until screen "story_choice"
        assert eval (game.turn_count == 1)
        assert eval (game.last_qte_success is True)
        assert eval (game.family_discussion == "比较了不同的办法")
        assert eval (story_state_is_stable())
        run FileSave(1, page="1", confirm=False)
        click "B."
        advance until screen "stats_change_popup"
        click "知道了"
        pause until screen "story_choice"
        assert eval (renpy.can_load("1-1"))
        assert "进阶" or "三百米"
        screenshot "teen-reasoning-hint.png"
        click "B."
        advance until screen "stats_change_popup"
        click "知道了"
        advance until screen "badge_unlock_popup"
        click "太棒了！"
        pause until screen "evaluation_screen"
        assert eval (get_play_stats()["total_plays"] == 1)
        assert eval (get_endings_unlocked()[-1]["ending_type"] == "大团圆式结局")
        screenshot "adventure-summary.png"
        click "生成家长报告"
        pause until screen "parent_report_screen"
        assert "保存报告"
        screenshot "parent-report.png"
        click "保存报告"
        advance until screen "evaluation_screen"
        assert eval (len(get_parent_reports()) == 1)
        click "生成家长报告"
        pause until screen "parent_report_screen"
        click "保存报告"
        advance until screen "evaluation_screen"
        assert eval (len(get_parent_reports()) == 1)
        click "返回主菜单"
        pause until screen "main_menu"
        run Show("ending_gallery")
        pause 0.3
        screenshot "ending-gallery.png"
        run Show("main_menu")

    testcase independent_settings_inputs:
        run Show("game_settings")
        pause 0.3
        $ renpy.set_screen_variable("powerup", "人物命运改写神器", screen="game_settings")
        $ renpy.restart_interaction()
        pause 0.3
        $ qa_original_scenario = renpy.get_screen("game_settings").scope["scenario_text"]
        run renpy.get_screen("game_settings").scope["fate_value"].Enable()
        type "help friends"
        assert eval (renpy.get_screen("game_settings").scope["fate_text"] == "help friends")
        assert eval (renpy.get_screen("game_settings").scope["scenario_text"] == qa_original_scenario)
        run Hide("game_settings")
        run Show("main_menu")

    testcase challenge_timeout:
        run Start("qa_timeout")
        pause until screen "qte_screen"
        pause 3.5
        assert screen "qte_screen"
        screenshot "qte-ready-without-timer.png"
        click "开始挑战"
        pause 3.5
        assert eval (qa_qte_result == "fail")
        advance until screen "main_menu"

    testcase challenge_keyboard_success:
        run Start("qa_timeout")
        pause until screen "qte_screen"
        click "开始挑战"
        keysym "K_SPACE"
        keysym "K_SPACE"
        keysym "K_SPACE"
        keysym "K_SPACE"
        pause 0.2
        assert eval (qa_qte_result == "success")
        advance until screen "main_menu"

    teardown:
        exit
