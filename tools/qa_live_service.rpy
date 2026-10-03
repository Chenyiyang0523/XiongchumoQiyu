# Local-only native UI test against the explicitly selected real GLM service.
# It is never included in client distributions or credential-free CI.
testsuite live_online:
    setup:
        $ _test.timeout = 900.0
        $ _test.screenshot_directory = __import__('os').environ['XCMQY_QA_OUTPUT']
        $ persistent.accounts = {'user_0': _make_empty_account_data('真实联网试玩', slot_index=0)}
        $ persistent.account_order = ['user_0']
        $ persistent.current_user = 'user_0'
        $ persistent.book_endpoint_v2 = __import__('os').environ['XCMQY_REAL_QA_ENDPOINT']
        $ game = StoryGame()
        run MainMenu(confirm=False)
        pause until screen 'main_menu'

    testcase real_first_action:
        run Start()
        pause until screen 'character_select'
        click '熊大'
        pause until screen 'book_setup'
        click '8 页'
        click id 'book_guardian_input'
        type "__XCMQY_QA_GUARDIAN__" id 'book_guardian_input'
        click '同意本次联网'
        click '连接'
        pause until eval (not book_busy)
        assert eval (bool(_book_token) and book_error=='已连接在线故事服务。')
        click '写下第一页'
        pause until screen 'book_reader'
        pause until eval (not book_busy)
        assert eval (book_story is not None and book_story['mock'] is False and book_story['state']['version']==1)
        assert eval (all(m['mock'] is False for m in book_story['usage']))
        screenshot '17-online-real-first.png'
        $ _qa_inter = next(i for i in book_story['pages'][-1]['interactions'] if any(book_action_available(a,i) for a in i['actions']))
        $ _qa_action = next(a for a in _qa_inter['actions'] if book_action_available(a,_qa_inter))
        $ book_items = _qa_action.get('inputs',[])
        $ book_order = _qa_inter.get('order',[])
        $ book_amount = -next(e['value'] for e in _qa_action['effects'] if e['op']=='resource') if _qa_action['verb']=='allocate' else 1
        run Function(book_stage_action,_qa_action,_qa_inter)
        assert eval (book_operations and book_story['state']['version']==1)
        click '确认行动 / 翻到下一页'
        pause until eval (not book_busy)
        assert eval (book_story['state']['version']==2 and len(book_story['pages'])==2 and not book_error)
        screenshot '18-online-real-action.png'
        $ __import__('pathlib').Path(__import__('os').environ['XCMQY_QA_OUTPUT'],'online-real-book.json').write_text(_book_json.dumps(book_story,ensure_ascii=False,indent=2),encoding='utf-8')
        click '上一页'
        assert eval (book_page_index==0 and book_story['state']['version']==2)
    teardown:
        exit
