# 仅复制到临时工程的 Ren'Py 视觉测试，不参与正式构建。

testsuite visual_qa:
    setup:
        $ game = StoryGame()
        $ quick_menu = False
        $ _test.screenshot_directory = __import__("os").environ["XCMQY_QA_OUTPUT"]
        $ persistent.accounts = {"user_0": _make_empty_account_data("森林小队", slot_index=0), "user_1": _make_empty_account_data("蜂蜜搭档", slot_index=1)}
        $ persistent.accounts["user_0"]["play_stats"]["total_plays"] = 3
        $ persistent.accounts["user_0"]["endings_unlocked"] = [{"title": "松风里的冒险"}]
        $ persistent.account_order = ["user_0", "user_1"]
        $ persistent.current_user = "user_0"

    testcase key_screens:
        run Show("account_select")
        pause until screen "account_select"
        pause 0.5
        screenshot "account-select.png"
        run Hide("account_select")

        run Show("character_select")
        pause until screen "character_select"
        pause 0.5
        screenshot "character-select.png"
        run Hide("character_select")

        run Show("game_settings")
        pause until screen "game_settings"
        pause 0.5
        screenshot "game-settings.png"
        run Hide("game_settings")

        $ renpy.scene()
        $ renpy.show("bg riverside")
        run Show("qte_screen", description="抓住绳子，帮助伙伴过河！", seconds=8)
        pause until screen "qte_screen"
        pause 0.5
        screenshot "qte-accessibility.png"
        run Hide("qte_screen")

    teardown:
        exit
