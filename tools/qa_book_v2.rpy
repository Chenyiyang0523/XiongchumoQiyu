# Native Ren'Py integration test, injected only into an isolated QA copy.
testsuite picturebook:
    setup:
        $ _test.timeout = 90.0
        $ _test.screenshot_directory = __import__("os").environ["XCMQY_QA_OUTPUT"]
        $ persistent.accounts = {"user_0": _make_empty_account_data("绘本测试", slot_index=0)}
        $ persistent.account_order = ["user_0"]
        $ persistent.current_user = "user_0"
        $ persistent.book_endpoint_v2 = "http://127.0.0.1:8000"
        $ game = StoryGame()
        run MainMenu(confirm=False)
        pause until screen "main_menu"

    testcase full_book:
        run Start()
        pause until screen "character_select"
        click "熊大"
        pause until screen "book_setup"
        screenshot "01-setup.png"
        click "8 页"
        click "亲子共玩"
        click id "book_guardian_input"
        type "local-dev-guardian" id "book_guardian_input"
        click "同意本次联网"
        click "连接"
        pause until eval (not book_busy)
        assert eval (bool(_book_token))
        screenshot "02-connected.png"
        click "写下第一页"
        pause until screen "book_reader"
        pause until eval (book_story is not None and bool(book_story.get("pages")))
        assert eval (book_story["state"]["version"] == 1)
        assert eval (get_user_page_range('user_0') == (10001,10004) and get_user_page_range('user_0',False) == (1,4))
        $ book_deliver(_book_epoch-1,book_identity()[0],None,'迟到的错误')
        assert eval (not book_error and not book_busy)
        screenshot "03-page-one.png"
        click id "book_hotspot_action.1.trail"
        assert eval (book_operations[0]['action_id']=='action.1.trail')
        run SetVariable('book_reason','我们先核对足迹，再决定路线。')
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 2)
        click "请伙伴一起确认"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 3)
        screenshot "04-evidence.png"
        click "按先后顺序摆好线索"
        assert eval (not book_operations)
        click "泥土上的痕迹先通往小桥。"
        click "远处的铃声晚于足迹出现。"
        click "按先后顺序摆好线索"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 4)
        click "收好地图，带着它核对"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 5)
        assert eval (book_story["state"]["items"]["item.map"]["owner"] == "player")
        click "背包与任务"
        pause until screen "book_notebook"
        screenshot "05-backpack.png"
        click "回到绘本"
        click "用地图核对路线"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 6)
        screenshot "06-allocation.png"
        click "分配2份时间一起检查"
        assert eval (not book_operations)
        click "分配1份时间做醒目标记"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 7)
        click "确认返回的约定，感谢伙伴"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story["state"]["version"] == 8)
        click "确认返回的约定，感谢伙伴"
        click "确认行动 / 翻到下一页"
        pause until eval (book_story.get("ending") is not None)
        screenshot "07-ending.png"
        click "发现、帮助与家庭回顾"
        pause until screen "book_family_review"
        screenshot "10-family-review.png"
        click "回到绘本"
        click "导出离线 HTML 绘本"
        assert eval (len(book_library().list()) == 1)
        click "上一页"
        assert eval (book_story["state"]["version"] == 9)
        screenshot "08-replay.png"
        click "保存并返回书架"
        pause until screen "book_shelf_screen"
        screenshot "09-shelf.png"
        click "绘本结局与勋章"
        pause until screen "book_collection"
        assert eval (get_current_account()['book_endings_v2'][book_story['id']] == book_story['ending'])
        screenshot "11-collection.png"
        click "回到原页"
        $ _qa_book_id = book_story['id']
        $ persistent.accounts['user_1'] = _make_empty_account_data('另一账户',slot_index=1)
        $ persistent.current_user = 'user_1'
        assert eval (not book_library().list())
        $ persistent.current_user = 'user_0'
        $ _book_token = ''
        $ book_story = None
        $ book_load(_qa_book_id)
        assert eval (book_story['state']['version']==9 and book_story['ending'] is not None)
        assert eval (book_story['pages'][0]['discussion']=='我们先核对足迹，再决定路线。')
    teardown:
        exit
