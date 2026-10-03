# Unified picturebook client. Legacy scripts remain only for legacy saves.
init -5 python:
    import sys as _book_sys
    import os as _book_os
    import json as _book_json
    import time as _book_time
    import uuid as _book_uuid
    from copy import deepcopy as _book_copy
    _book_sys.path.insert(0, config.gamedir)
    from storybook.client import Client as _BookClient, Library as _BookLibrary, ClientError as _BookError, new_key as _book_key
    from storybook.engine import apply_operations as _book_preview, RuleError as _BookRule
    from storybook.export import export_html as _book_export
    from storybook.review import record_completion as _book_record_completion, reflection as _book_reflection
    from storybook.layout import rectangles as _book_rectangles, uses_layers as _book_uses_layers
    with renpy.file("storybook/asset_manifest.json") as _manifest_file:
        BOOK_MANIFEST = _book_json.load(_manifest_file)["assets"]
    _book_epoch = 0
    _book_token = ""
    _book_token_account = ""
    _book_token_endpoint = ""
    BOOK_PHASES = {"queued": "等待生成", "planning": "规划故事", "generating": "编写新页", "reviewing": "检查事实与表达", "committing": "保存绘本", "complete": "完成", "failed": "生成暂停"}

    def book_identity():
        account = get_current_account()
        if account is None:
            raise _BookError("请先选择账户。")
        if not account.get("cloud_account_v2"):
            account["cloud_account_v2"] = _book_key()
            account["cloud_secret_v2"] = _book_key() + _book_key()
            renpy.save_persistent()
        return account["cloud_account_v2"], account["cloud_secret_v2"]

    def book_library():
        return _BookLibrary(config.savedir, book_identity()[0])

    def book_asset(aid):
        return BOOK_MANIFEST[aid]["path"]

    def book_at_page():
        if book_page_index == len(book_story['pages'])-1 and not book_story.get('ending') and book_operations:
            try:
                return _book_preview(book_story, book_operations, book_reason)[0]
            except _BookRule:
                pass
        return book_story['pages'][book_page_index].get('state_snapshot', book_story['state'])

    def book_plain(value):
        return str(value).replace('[', '[[').replace('{', '{{')

    def book_refresh_account(story):
        account = get_current_account()
        account["books_v2"][story["id"]] = {"title": story["blueprint"]["title"], "status": story["status"], "mock": story.get("mock", False)}
        if story.get("ending"):
            _book_record_completion(account, story)
            # Exactly one shared ending record drives the book, report and badge view.
            account["book_endings_v2"][story["id"]] = _book_copy(story["ending"])
            if story["id"] not in [b["id"] for b in account["recent_books_v2"]]:
                account["recent_books_v2"].append({"id": story["id"], "theme": story["blueprint"]["theme"], "arc": story["blueprint"]["arc"], "solution": story["ending"]["solution"]})
                account["recent_books_v2"] = account["recent_books_v2"][-10:]
        renpy.save_persistent()

    def book_deliver(epoch, aid, result, error):
        global book_busy, book_error, book_story, book_page_index, book_phase, book_clarifications, book_clarification_job, book_owner
        if epoch != _book_epoch or not get_current_account() or book_identity()[0] != aid:
            return
        book_busy = False
        book_error = error
        book_phase = ""
        if result:
            if result.get("clarification"):
                book_clarifications = result["clarification"]
                book_clarification_job = result["clarification_job"]
                book_error = "我有几种理解，请选择你想表达的行动；原来的页面还在。"
            elif result.get("schema_version") == 2 and result.get("blueprint"):
                book_story = result
                book_owner = aid
                book_page_index = len(result["pages"]) - 1
                book_reset_operations()
                book_refresh_account(result)
        renpy.restart_interaction()

    def book_status(epoch, aid, phase):
        global book_phase
        if epoch == _book_epoch and get_current_account() and book_identity()[0] == aid:
            book_phase = BOOK_PHASES.get(phase, phase)
            renpy.restart_interaction()

    def book_background(operation, payload=None):
        global _book_epoch, book_busy, book_error, book_phase, book_owner
        if book_busy:
            return
        aid, secret = book_identity()
        if operation != 'connect' and operation != 'create' and book_owner != aid:
            renpy.notify('请从当前账户书架打开绘本。')
            return
        if operation == 'create':
            book_owner = aid
        epoch = _book_epoch = _book_epoch + 1
        endpoint = persistent.book_endpoint_v2 or _book_os.environ.get("XCMQY_STORY_ENDPOINT", "http://127.0.0.1:8000")
        client = _BookClient(endpoint, _book_token if operation != "connect" and _book_token_account == aid and _book_token_endpoint == endpoint else "")
        library = book_library()
        stable = _book_copy(book_story) if book_story else None
        book_busy, book_error, book_phase = True, "", "连接绘本服务"
        if operation == "connect":
            payload = {"account_id": aid, "account_secret": secret, "guardian_code": payload, "consent": True}
        # Persist the exact outgoing action and idempotency key BEFORE making a request.
        checkpoint = _book_copy(stable) if stable else {"schema_version": 2, "id": payload.get("idempotency_key", _book_key()), "saved_at": _book_time.time()}
        if operation in ("create", "turn"):
            checkpoint["pending_client"] = {"operation": operation, "payload": payload, "endpoint": endpoint}
            library.save(checkpoint)
        def work():
            global _book_token, _book_token_account, _book_token_endpoint
            try:
                if operation == "connect":
                    session = client.request("/v2/sessions", payload)
                    if epoch == _book_epoch:
                        _book_token, _book_token_account, _book_token_endpoint = session["access_token"], aid, endpoint
                    message = "已连接开发模拟服务。" if session["mock"] else "已连接在线故事服务。"
                    renpy.invoke_in_main_thread(book_deliver, epoch, aid, None, message)
                    return
                if operation == "restore":
                    restored = client.request("/v2/stories/" + stable["id"])
                    restored["saved_at"] = _book_time.time()
                    pending = restored.get("pending")
                    if pending:
                        restored['pending_client'] = {'operation':'turn','payload':pending['request'],'job_id':pending['job_id'],'endpoint':endpoint}
                    library.save(restored)
                    if not pending or pending["phase"] == "failed":
                        renpy.invoke_in_main_thread(book_deliver, epoch, aid, restored, "有一次待重试行动。" if pending else "")
                        return
                    jid = pending["job_id"]
                elif operation == "retry":
                    jid = payload["job_id"]
                    client.request("/v2/jobs/" + jid + "/retry", {})
                else:
                    route = "/v2/stories" if operation == "create" else "/v2/stories/" + stable["id"] + "/actions"
                    jid = client.request(route, payload)["job_id"]
                    checkpoint["pending_client"]["job_id"] = jid
                    library.save(checkpoint)
                deadline = _book_time.monotonic() + float(_book_os.environ.get('XCMQY_JOB_POLL_TIMEOUT', '600'))
                while True:
                    if epoch != _book_epoch:
                        return
                    if _book_time.monotonic() > deadline:
                        raise _BookError('等待新页超时；行动已保留，可以恢复或重试。')
                    job = client.request("/v2/jobs/" + jid)
                    renpy.invoke_in_main_thread(book_status, epoch, aid, job["phase"])
                    if job["phase"] == "failed":
                        raise _BookError("新页未通过生成或检查，当前页面已保存。可以重试这次行动。")
                    if job["phase"] == "complete":
                        result = job["result"]
                        if result.get("clarification"):
                            if stable:
                                library.save(stable)
                            renpy.invoke_in_main_thread(book_deliver, epoch, aid, result, "")
                            return
                        restored = client.request("/v2/stories/" + result["story_id"])
                        restored["saved_at"] = _book_time.time()
                        library.save(restored)
                        if checkpoint["id"] != restored["id"]:
                            library.filename(checkpoint["id"]).unlink(missing_ok=True)
                        renpy.invoke_in_main_thread(book_deliver, epoch, aid, restored, "")
                        return
                    _book_time.sleep(0.5)
            except Exception as exc:
                # Do not expose remote messages or credentials. Keep checkpoint and stable book.
                renpy.invoke_in_main_thread(book_deliver, epoch, aid, None, str(exc) if isinstance(exc, _BookError) else "服务暂时不可用，当前绘本和待处理行动已保留。")
        renpy.invoke_in_thread(work)

    def book_reset_operations():
        global book_operations, book_input, book_reason, book_feedback, book_order, book_clarifications, book_items, book_amount
        book_operations, book_input, book_reason, book_feedback, book_order, book_clarifications = [], "", "", "", [], []
        book_items, book_amount = [], 1

    def book_operation_sequence(action, interaction, operation):
        group = {a['id'] for a in interaction['actions']}
        ops, replaced = [], False
        for old in book_operations:
            if old['action_id'] in group:
                if not replaced:
                    ops.append(operation)
                    replaced = True
            else:
                ops.append(old)
        if not replaced:
            ops.append(operation)
        return ops

    def book_stage_action(action, interaction):
        global book_operations, book_feedback
        operation = {"action_id": action["id"]}
        if action["verb"] == "allocate":
            operation["amount"] = book_amount
        if action.get('inputs'):
            operation['items'] = list(book_items)
        if interaction.get("order_action") == action["id"]:
            operation["order"] = list(book_order)
        ops = book_operation_sequence(action, interaction, operation)
        try:
            _book_preview(book_story, ops, book_reason)
            book_operations = ops
            book_feedback = "已准备：" + action["feedback"]
        except _BookRule:
            book_feedback = "这个操作的条件还不满足。请检查线索顺序、物品或剩余资源。"
        renpy.restart_interaction()

    def book_action_available(action, interaction):
        operation = {'action_id': action['id'], 'items': action.get('inputs', [])}
        if action['verb'] == 'allocate':
            operation['amount'] = -next(e['value'] for e in action['effects'] if e['op'] == 'resource')
        if interaction.get('order_action') == action['id']:
            operation['order'] = interaction['order']
        try:
            _book_preview(book_story, book_operation_sequence(action, interaction, operation), book_reason)
            return True
        except _BookRule:
            return False

    def book_clear_staged():
        global book_operations, book_feedback, book_items, book_order
        book_operations, book_items, book_order = [], [], []
        book_feedback = '本页操作已撤回，可以重新安排。'
        renpy.restart_interaction()

    def book_select_clue(cid):
        global book_order
        book_order = [c for c in book_order if c != cid] if cid in book_order else book_order + [cid]
        renpy.restart_interaction()

    def book_select_item(iid):
        global book_items
        book_items = [i for i in book_items if i != iid] if iid in book_items else book_items + [iid]
        renpy.restart_interaction()

    def book_submit():
        if not book_operations and not book_input.strip():
            return
        payload = {"version": book_story["state"]["version"], "idempotency_key": _book_key(),
                   "operations": _book_copy(book_operations), "text": book_input.strip()[:200], "reason": book_reason.strip()[:200]}
        book_background("turn", payload)

    def book_confirm_understanding(action):
        book_background("turn", {"version": book_story["state"]["version"], "idempotency_key": _book_key(), "operations": [], "text": "", "reason": book_reason.strip()[:200], "clarification_job": book_clarification_job, "clarification_action": action["id"]})

    def book_retry():
        try:
            pending = book_library().load(book_story["id"])["pending_client"] if book_story else next(b["pending_client"] for b in book_library().list() if b.get("pending_client") and not b.get("blueprint"))
            if pending.get("endpoint") != persistent.book_endpoint_v2:
                renpy.notify("请连接保存行动时使用的服务地址，再重试这次行动。")
                return
            if pending.get("job_id"):
                book_background("retry", pending)
            else:
                book_background(pending["operation"], pending["payload"])
        except (KeyError, StopIteration):
            if book_story:
                book_background("restore")

    def book_load(sid):
        global _book_epoch, book_story, book_page_index, book_busy, book_error, book_owner
        _book_epoch += 1
        book_busy = False
        book_story = book_library().load(sid)
        book_owner = book_identity()[0]
        book_page_index = len(book_story.get("pages", [])) - 1
        book_error = "有一次待处理行动，可以重试或联网恢复。" if book_story.get('pending_client') or book_story.get('pending') else ""
        book_reset_operations()

    def book_export_current():
        global book_feedback
        target = book_library().path / "exports" / (book_story["id"] + ".html")
        def read_asset(path):
            with renpy.file(path) as resource:
                return resource.read()
        _book_export(book_story, target, read_asset)
        book_feedback = "离线绘本已导出：" + str(target)
        renpy.notify("离线 HTML 绘本已导出到本账户绘本目录。")

default book_story = None
default book_owner = None
default book_v2_mode = False
default book_page_index = 0
default book_busy = False
default book_error = ""
default book_phase = ""
default book_operations = []
default book_input = ""
default book_reason = ""
default book_feedback = ""
default book_order = []
default book_clarifications = []
default book_clarification_job = ""
default book_items = []
default book_amount = 1
default persistent.book_endpoint_v2 = None

label start:
    jump book_start

label book_start:
    $ book_v2_mode = True
    $ quick_menu = False
    $ _book_epoch += 1
    $ book_busy = False
    $ book_story = None
    $ book_owner = None
    $ book_reset_operations()
    scene bg forest
    call screen character_select
    if not _return:
        return
    $ selected_character = _return
    call screen book_setup
    if _return is None:
        return
    $ book_settings = _return
    $ book_background("create", {"settings": book_settings, "idempotency_key": _book_key()})
    jump book_read

label book_read:
    call screen book_reader
    if _return == "shelf":
        jump book_shelf
    return

label book_shelf:
    $ book_v2_mode = True
    if not get_current_account():
        return
    call screen book_shelf_screen
    if _return:
        $ book_load(_return)
        if book_story.get("blueprint"):
            jump book_read
        else:
            $ book_retry()
            jump book_read
    return

style book_text is default:
    font "SourceHanSansLite.ttf"
    size 30
    color "#254737"
style book_button is button:
    background Solid("#E6EDDD")
    hover_background Solid("#CADDBB")
    selected_background Solid("#BBD6A8")
    padding (22, 14)
style book_button_text is book_text:
    size 27
    hover_color "#193A2A"
style book_input is input:
    size 27
    color "#254737"

screen book_setup():
    tag menu
    default theme = "森林探险"
    default age = "6-8"
    default length = 12
    default parent = False
    default endpoint = persistent.book_endpoint_v2 or _book_os.environ.get("XCMQY_STORY_ENDPOINT", "http://127.0.0.1:8000")
    default guardian = ""
    default consent = False
    $ theme_value = ScreenVariableInputValue("theme", default=True)
    $ endpoint_value = ScreenVariableInputValue("endpoint", default=False)
    $ guardian_value = ScreenVariableInputValue("guardian", default=False)
    add Solid("#F3EFDF")
    frame:
        background None
        xalign .5 yalign .5 xsize 1500
        vbox:
            spacing 18
            text "开启一本新的森林绘本" style "book_text" size 48 font "ZCOOLKuaiLe-Regular.ttf"
            text "选择主题，或者写下你想遇见的事情。" style "book_text"
            hbox:
                spacing 16
                for title in ["森林探险", "寻宝之旅", "拯救行动", "友谊考验"]:
                    textbutton title style "book_button" action SetScreenVariable("theme", title)
            button:
                background Solid("#FFFDF4") padding (20, 12) xfill True
                action theme_value.Enable()
                input id "book_theme_input" value theme_value length 100 style "book_input" xfill True
            hbox:
                spacing 18
                textbutton "6-8 岁 / 轻松阅读" style "book_button" selected age == "6-8" action SetScreenVariable("age", "6-8")
                textbutton "9-12 岁 / 更多推理" style "book_button" selected age == "9-12" action SetScreenVariable("age", "9-12")
                textbutton "亲子共玩" style "book_button" selected parent action ToggleScreenVariable("parent")
            hbox:
                spacing 18
                for count in [8, 12, 16, 20]:
                    textbutton (str(count) + " 页") style "book_button" selected length == count action SetScreenVariable("length", count)
            text ("阅读参考：约 " + str(length) + "–" + str(length*2) + " 分钟，按自己的节奏体验。") style "book_text" size 24
            text "监护人连接故事服务" style "book_text" size 34
            text "故事设定、玩家行动与讨论理由将发送至所连接的服务。已有页面保存在本机。" style "book_text" size 25
            button:
                background Solid("#FFFDF4") padding (20, 12) xfill True
                action endpoint_value.Enable()
                input id "book_endpoint_input" value endpoint_value length 200 style "book_input" xfill True
            hbox:
                spacing 18
                button:
                    background Solid("#FFFDF4") padding (20, 12) xsize 600
                    action guardian_value.Enable()
                    input id "book_guardian_input" value guardian_value length 128 mask "*" style "book_input" xfill True
                textbutton "同意本次联网" style "book_button" selected consent action ToggleScreenVariable("consent")
                textbutton "连接" style "book_button":
                    sensitive consent and len(guardian) >= 8 and not book_busy
                    action [SetField(persistent, "book_endpoint_v2", endpoint), Function(book_background, "connect", guardian)]
            if book_busy:
                text book_phase style "book_text" size 24
            if book_error:
                text book_error style "book_text" size 24
            hbox:
                spacing 18
                textbutton "写下第一页" style "book_button":
                    sensitive bool(_book_token) and _book_token_account == book_identity()[0] and _book_token_endpoint == endpoint and consent and not book_busy and bool(theme.strip())
                    action Return({"theme": theme.strip(), "character": selected_character, "age": age, "pages": length, "parent_mode": parent, "assets": list(BOOK_MANIFEST)})
                textbutton "返回" style "book_button" action Return(None)

screen book_reader():
    tag menu
    $ thought_value = VariableInputValue("book_input", default=False)
    $ reason_value = VariableInputValue("book_reason", default=False)
    add Solid("#F3EFDF")
    if book_story and book_owner != book_identity()[0]:
        vbox:
            xalign .5 yalign .5 spacing 30
            text '账户已经切换，请打开当前账户的绘本。' style 'book_text' size 40
            textbutton '返回书架' style 'book_button' action Return('shelf')
    elif book_story and book_story.get("blueprint"):
        $ page = book_story["pages"][book_page_index]
        $ art = page["illustration"]
        $ live = book_page_index == len(book_story["pages"])-1 and not book_story.get("ending") and book_story["status"] != "continued"
        frame:
            xpos 40 ypos 24 xsize 1240 ysize 88 background None
            hbox:
                spacing 22
                text book_plain(book_story["blueprint"]["title"]) style "book_text" size 38 substitute False
                if book_story.get("mock"):
                    text "开发模拟绘本" style "book_text" size 25 color "#946326"
        fixed:
            xpos 50 ypos 125 xsize 1200 ysize 675
            $ character_rects, prop_rects = _book_rectangles(art, BOOK_MANIFEST)
            $ layered = _book_uses_layers(art, page['interactions'])
            add Transform(book_asset(art['scene'] if layered else art['key_art']), xysize=(1200,675), fit="cover")
            if layered:
                for aid, x, y, w, h in character_rects + prop_rects:
                    add Transform(book_asset(aid), xysize=(int(w*1200),int(h*675)), fit="contain") xpos int(x*1200) ypos int(y*675)
            if live and not book_busy:
                for index, inter in enumerate(page["interactions"]):
                    if inter["kind"] == "observe":
                        for n, action in enumerate(inter["actions"]):
                            $ target_rect = next((r for r in prop_rects + character_rects if r[0] == action.get('hotspot')), None)
                            if target_rect:
                                button:
                                    id ('book_hotspot_' + action['id'])
                                    xpos int(target_rect[1]*1200) ypos int(target_rect[2]*675)
                                    xsize int(target_rect[3]*1200) ysize int(target_rect[4]*675)
                                    padding (0,0) background None hover_background Solid('#FFF4A14D')
                                    hovered SetVariable('book_feedback', action['label'])
                                    action Function(book_stage_action, action, inter)
                            else:
                                textbutton ("观察 " + book_plain(action["label"])) style "book_button" xsize 530 text_size 23 xpos (40+(n%2)*580) ypos (40+(n//2)*85+index*85) action Function(book_stage_action, action, inter)
        frame:
            xpos 50 ypos 815 xsize 1200 ysize 220 background Solid("#FFFDF5") padding (26, 18)
            vbox:
                spacing 10
                text book_plain(page["title"]) style "book_text" size 34 font "ZCOOLKuaiLe-Regular.ttf" substitute False
                text book_plain(page["text"]) style "book_text" size (30 if book_story["settings"]["age"] == "6-8" else 25) line_spacing 4 substitute False
        frame:
            xpos 1300 ypos 30 xsize 580 ysize 1015 background Solid("#FFFDF5") padding (24, 24)
            viewport:
                mousewheel True scrollbars "vertical" pagekeys True
                ymaximum 725
                vbox:
                    spacing 18
                    text "我们的目标" style "book_text" size 34
                    text book_plain(book_story["blueprint"]["goal"]) style "book_text" size 26 substitute False
                    hbox:
                        spacing 14
                        textbutton "线索册" style "book_button" action Show("book_notebook", kind="clues")
                        textbutton "背包与任务" style "book_button" action Show("book_notebook", kind="items")
                    if book_story.get('ending'):
                        textbutton '发现、帮助与家庭回顾' style 'book_button' action Show('book_family_review')
                    if live:
                        for inter in page["interactions"]:
                            text book_plain(inter["instruction"]) style "book_text" size 26 substitute False
                            if inter.get("order"):
                                for cid in reversed(inter["order"]):
                                    textbutton book_plain(book_story["blueprint"]["clues"][cid]) style "book_button" selected cid in book_order action Function(book_select_clue, cid)
                                text ("已排列 " + str(len(book_order)) + " 条线索；再次点击可移除。") style "book_text" size 23
                            if inter['kind'] == 'items':
                                for iid, item in book_at_page()['items'].items():
                                    if item['owner'] == 'player':
                                        textbutton ("物品：" + book_plain(item['name'])) style "book_button" selected iid in book_items action Function(book_select_item, iid)
                                if any(a.get('inputs') for a in inter['actions']):
                                    text '点击所需物品，再选择使用或组合办法。' style 'book_text' size 23
                            if inter['kind'] == 'allocation':
                                hbox:
                                    spacing 12
                                    textbutton '-' style 'book_button' sensitive book_amount > 1 action SetVariable('book_amount', book_amount-1)
                                    text ('分配 ' + str(book_amount) + ' 份') style 'book_text' size 25 yalign .5
                                    textbutton '+' style 'book_button' sensitive book_amount < 20 action SetVariable('book_amount', book_amount+1)
                            for action in inter["actions"]:
                                textbutton book_plain(action["label"]) style "book_button":
                                    sensitive not book_busy and book_action_available(action, inter)
                                    selected any(op["action_id"] == action["id"] for op in book_operations)
                                    action Function(book_stage_action, action, inter)
                        text "我有自己的想法" style "book_text" size 28
                        if book_operations:
                            textbutton '重新安排本页' style 'book_button' action Function(book_clear_staged)
                        button:
                            background Solid("#EDF1E5") padding (16, 12) xfill True
                            action thought_value.Enable()
                            input id "book_thought_input" value thought_value length 200 style "book_input" xfill True
                        if book_story["settings"]["parent_mode"]:
                            text "我们的理由 / 另一种办法" style "book_text" size 25
                            button:
                                background Solid("#EDF1E5") padding (16, 12) xfill True
                                action reason_value.Enable()
                                input id "book_reason_input" value reason_value length 200 style "book_input" xfill True
                        for action in book_clarifications:
                            textbutton ("我想表达：" + book_plain(action["label"])) style "book_button" sensitive not book_busy action Function(book_confirm_understanding, action)
                    elif book_story.get("ending"):
                        text book_plain(book_story["ending"]["title"]) style "book_text" size 34
                        text book_plain(book_story["ending"]["text"]) style "book_text" size 26 substitute False
                        text "发现与帮助都来自这次真实行动。" style "book_text" size 24
                        for eid in book_story["ending"]["evidence"]:
                            text book_plain(next(e["description"] for e in book_story["events"] if e["id"] == eid)) style "book_text" size 23 substitute False
                    elif book_story["status"] == "continued":
                        text "待续 / 已到本次页数上限。未完成的任务已保留。" style "book_text" size 28
                    if book_feedback:
                        text book_plain(book_feedback) style "book_text" size 23 substitute False
                    if book_busy:
                        text (book_phase + "……已有页面可以回看。") style "book_text" size 25
                    if book_error:
                        text book_error style "book_text" size 24
                        textbutton "重试待处理行动" style "book_button" sensitive not book_busy action Function(book_retry)
                    textbutton "联网恢复" style "book_button" sensitive not book_busy action Function(book_background, "restore")
                    textbutton '监护人连接服务' style 'book_button' sensitive not book_busy action Show('book_connection')
        frame:
            xpos 1300 ypos 810 xsize 580 ysize 240 background Solid("#FFFDF5") padding (24, 12)
            vbox:
                spacing 10
                if live:
                    textbutton "确认行动 / 翻到下一页" style "book_button":
                        sensitive not book_busy and (bool(book_operations) or bool(book_input.strip()))
                        action Function(book_submit)
                hbox:
                    spacing 8
                    textbutton "上一页" style "book_button" sensitive book_page_index > 0 action SetVariable("book_page_index", book_page_index-1)
                    text (str(book_page_index+1)+" / "+str(len(book_story["pages"]))) style "book_text" size 25 yalign .5
                    textbutton "下一页" style "book_button" sensitive book_page_index < len(book_story["pages"])-1 action SetVariable("book_page_index", book_page_index+1)
                hbox:
                    spacing 10
                    textbutton "导出离线 HTML 绘本" style "book_button" text_size 22 action Function(book_export_current)
                    textbutton "保存并返回书架" style "book_button" text_size 22 action Return("shelf")
    else:
        vbox:
            xalign .5 yalign .5 spacing 30
            text (book_phase or "正在准备第一页……") style "book_text" size 42
            if book_error:
                text book_error style "book_text" size 28
                textbutton "重试" style "book_button" sensitive not book_busy action Function(book_retry)
            textbutton "监护人连接服务" style "book_button" action Show("book_connection")
            textbutton "返回书架" style "book_button" action Return("shelf")

screen book_notebook(kind):
    modal True
    $ page_state = book_at_page()
    add Solid("#183126AA")
    frame:
        xalign .5 yalign .5 xsize 1100 ysize 800 background Solid("#FFFDF3") padding (40, 36)
        vbox:
            spacing 20
            text ("线索册" if kind == "clues" else "背包、任务与约定") style "book_text" size 40
            viewport:
                mousewheel True scrollbars "vertical" ymaximum 610
                vbox:
                    spacing 18
                    if kind == "clues":
                        for cid in page_state["knowledge"]:
                            text ("线索：" + book_plain(book_story["blueprint"]["clues"][cid])) style "book_text" size 28 substitute False
                    else:
                        for item in page_state["items"].values():
                            text (book_plain(item["name"]) + " / " + ("在我的背包里" if item["owner"] == "player" else "已经使用" if item["owner"] == "consumed" else "尚待制作" if item['owner'] == 'unmade' else "由伙伴保管" if item["owner"] in page_state["characters"] else "留在场景中")) style "book_text" size 28 substitute False
                        for quest in book_story["blueprint"]["quests"]:
                            if quest['id'] in page_state['quests']:
                                text (("完成：" if page_state["quests"][quest["id"]] == "complete" else "待办：") + book_plain(quest["title"])) style "book_text" size 28 substitute False
                        for name, amount in page_state["resources"].items():
                            text (book_plain(name) + "：" + str(amount)) style "book_text" size 28
                        for pid, done in page_state["promises"].items():
                            text ("约定 " + book_plain(pid) + (" / 已兑现" if done else " / 待兑现")) style "book_text" size 27
            textbutton "回到绘本" style "book_button" action Hide("book_notebook")

screen book_shelf_screen():
    tag menu
    add Solid("#F3EFDF")
    frame:
        xalign .5 yalign .5 xsize 1550 ysize 900 background None
        vbox:
            spacing 24
            text "我的森林绘本" style "book_text" size 48 font "ZCOOLKuaiLe-Regular.ttf"
            text "已读页面离线保留；回看不会改变故事。新旧存档分别保存。" style "book_text" size 28
            viewport:
                mousewheel True scrollbars "vertical" ymaximum 650
                vbox:
                    spacing 16
                    for book in book_library().list():
                        textbutton (book_plain(book.get("blueprint", {}).get("title", "等待生成的绘本")) + " / " + ("已完成" if book.get("ending") else "待续" if book.get("status") == "continued" else "进行中") + (" / 开发模拟" if book.get("mock") else "")):
                            style "book_button"
                            action Return(book["id"])
            textbutton "返回" style "book_button" action Return(None)
            textbutton "绘本结局与勋章" style "book_button" action Show("book_collection")

screen book_collection():
    modal True
    $ collection_account = get_current_account() or {}
    add Solid('#183126CC')
    frame:
        xalign .5 yalign .5 xsize 1400 ysize 950 background Solid('#FFFDF3') padding (40,36)
        vbox:
            spacing 20
            text '绘本结局与勋章' style 'book_text' size 44
            viewport:
                mousewheel True scrollbars 'vertical' ymaximum 720
                vbox:
                    spacing 20
                    if not collection_account.get('book_endings_v2'):
                        text '完成绘本后，你的发现、帮助与解决办法会留在这里。' style 'book_text' size 28
                    for sid, ending in collection_account.get('book_endings_v2', {}).items():
                        $ summary = collection_account.get('books_v2', {}).get(sid, {})
                        $ report = collection_account.get('family_reviews_v2', {}).get(sid, {})
                        text (book_plain(summary.get('title', ending['title'])) + (' / 开发模拟' if summary.get('mock') else '')) style 'book_text' size 32 substitute False
                        text book_plain(ending['text']) style 'book_text' size 27 substitute False
                        text ('解决办法：' + book_plain(ending['solution'])) style 'book_text' size 25 substitute False
                        for action in report.get('actions', []):
                            text book_plain(action['description']) style 'book_text' size 23 substitute False
                        $ badge = collection_account.get('book_badges_v2', {}).get(sid, {})
                        if badge:
                            text ('勋章：' + book_plain(badge['title'])) style 'book_text' size 26 substitute False
            textbutton '回到原页' style 'book_button' action Hide('book_collection')

screen book_family_review():
    modal True
    $ report = _book_reflection(book_story)
    add Solid('#183126AA')
    frame:
        xalign .5 yalign .5 xsize 1160 ysize 850 background Solid('#FFFDF3') padding (40,36)
        vbox:
            spacing 20
            text '我们怎样完成这本绘本' style 'book_text' size 40
            viewport:
                mousewheel True scrollbars 'vertical' ymaximum 650
                vbox:
                    spacing 16
                    text '发现了什么' style 'book_text' size 32
                    for finding in report['discoveries']:
                        text book_plain(finding) style 'book_text' size 27 substitute False
                    text ('帮助了谁：'+'、'.join(report['helped'])) style 'book_text' size 30 substitute False
                    text book_plain(report['ending']['solution']) style 'book_text' size 27 substitute False
                    for action in report['actions']:
                        text book_plain(action['description']) style 'book_text' size 26 substitute False
                        if action['reason']:
                            text ('我们当时的理由：'+book_plain(action['reason'])) style 'book_text' size 24 substitute False
                    text report['badge']['title'] style 'book_text' size 28
            textbutton '回到绘本' style 'book_button' action Hide('book_family_review')

screen book_connection():
    modal True
    default endpoint = persistent.book_endpoint_v2 or 'http://127.0.0.1:8000'
    default guardian = ''
    default consent = False
    $ endpoint_value = ScreenVariableInputValue('endpoint',default=False)
    $ guardian_value = ScreenVariableInputValue('guardian',default=True)
    add Solid('#183126AA')
    frame:
        xalign .5 yalign .5 xsize 1300 background Solid('#FFFDF3') padding (40,36)
        vbox:
            spacing 25
            text '监护人连接故事服务' style 'book_text' size 40
            text '继续故事时，行动与讨论理由将发送至这个服务。已有页面可离线阅读。' style 'book_text' size 26
            button:
                background Solid('#E6EDDD') padding (20,12) xfill True action endpoint_value.Enable()
                input value endpoint_value length 200 style 'book_input' xfill True
            text '监护人访问码' style 'book_text' size 28
            button:
                background Solid('#E6EDDD') padding (20,12) xfill True action guardian_value.Enable()
                input value guardian_value length 128 mask '*' style 'book_input' xfill True
            hbox:
                spacing 20
                textbutton '同意本次联网' style 'book_button' selected consent action ToggleScreenVariable('consent')
                textbutton '连接' style 'book_button' sensitive consent and len(guardian)>=8 and not book_busy action [SetField(persistent,'book_endpoint_v2',endpoint),Function(book_background,'connect',guardian)]
                textbutton '回到绘本' style 'book_button' action Hide('book_connection')
            text (book_phase or book_error) style 'book_text' size 25
