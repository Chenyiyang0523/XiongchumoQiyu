# 熊出没奇遇 — 游戏流程
# 完整 label 定义：开始 → 选角 → 设置 → AI 剧情循环 → 评价
# 支持：段落级流式渲染 + 后台预生成

# ============================================================
# 游戏入口
# ============================================================

label start:

    $ quick_menu = False

    # 显示森林背景
    scene bg forest with dissolve

    # 播放背景音乐（循环）
    play music "audio/music.mp3" fadein 2.0

    "欢迎来到《熊出没奇遇》！"
    "化身你喜爱的角色，在狗熊岭展开一段奇妙冒险！"

    jump character_selection


# ============================================================
# 角色选择
# ============================================================

label character_selection:

    call screen character_select

    $ selected_character = _return

    if not selected_character:
        return

    "好的！你将扮演 [selected_character]！"

    jump settings_phase


# ============================================================
# 游戏设置
# ============================================================

label settings_phase:

    call screen game_settings

    $ settings = _return
    if settings == "__back__":
        jump character_selection
    $ story_scenario = settings["scenario"]
    $ story_mode = settings["mode"]
    $ story_difficulty = settings["difficulty"]
    $ story_duration = settings["duration"]
    $ story_powerup = settings["powerup"]
    $ story_fate_text = settings["fate_text"]
    $ story_ending_type = settings["ending_type"]
    $ story_online_enabled = settings.get("online_enabled", False)

    # 使用 Ren'Py/操作系统自带自读，不上传对话到第三方 TTS。
    $ tts_manager.enabled = settings.get("tts_enabled", False)
    $ _preferences.self_voicing = tts_manager.enabled

    "情景：[story_scenario]"
    "准备好了吗？冒险即将开始！"

    jump story_begin


# ============================================================
# 故事启动（流式 AI 首次调用）
# ============================================================

label story_begin:

    # 本地故事引擎始终可用，云端为玩家显式选择的可选增强。
    $ game.start_stream(
        selected_character,
        story_scenario,
        story_duration,
        story_mode,
        story_difficulty,
        story_powerup,
        story_fate_text,
        story_ending_type,
        story_online_enabled,
    )

    # 等待首个段落就绪
    call screen loading_animation

    # 检查是否有错误
    if game.ai_error:
        call screen ai_error_screen(game.ai_error)
        if _return == "retry":
            jump story_begin
        else:
            return

    if game.ai_notice:
        $ renpy.notify(game.ai_notice)

    # 显示四维属性侧边栏和百科提示
    show screen stats_overlay
    show screen encyclopedia_hint
    $ quick_menu = True

    # 显示初始场景的知识热点
    $ _init_sid = game.current_scene_id or "forest"
    if _init_sid in SCENE_KNOWLEDGE_ITEMS:
        show screen scene_knowledge_overlay(scene_id=_init_sid)

    jump display_stream


# ============================================================
# 流式渲染：循环消费段落队列
# ============================================================

label display_stream:

    # 循环渲染段落，直到流结束且队列清空
    python:
        while not game.is_stream_complete():
            if game.has_pending_segments():
                seg = game.pop_segment()
                render_stream_segment(seg)
            else:
                # 队列空但流未结束，短暂等待
                renpy.pause(0.2, hard=True)

    # 检查流式中途是否出错
    if game.ai_error and not game._full_response:
        call screen ai_error_screen(game.ai_error)
        if _return == "retry":
            jump story_begin
        else:
            return

    # 流式完成，将完整响应存入消息历史
    $ game.finalize_stream_response()

    # 从完整响应中提取选项
    $ current_options = extract_options(game._full_response)

    jump player_turn


# ============================================================
# 玩家回合
# ============================================================

label player_turn:

    # 检查故事是否已结束
    if game.ended:
        jump story_end

    # 先反馈上一轮结果，再让玩家做新选择。
    if game._pending_stat_popup:
        call screen stats_change_popup(changes=game._pending_stat_popup)
        $ game._pending_stat_popup = None

    if game._eq_feedback_pending:
        $ game._eq_feedback_pending = False
        python:
            _eq_idx = 0
            _eq_available = [i for i in range(len(EQ_REFLECTIONS)) if i not in game._eq_used_indices]
            if _eq_available:
                _eq_idx = random.choice(_eq_available)
                game._eq_used_indices.append(_eq_idx)
        call screen eq_feedback_screen(reflection=EQ_REFLECTIONS[_eq_idx])

    if game._game_mode == "亲子共玩" and game.turn_count == 1 and not getattr(game, "family_discussion", ""):
        call screen family_discussion
        $ game.family_discussion = _return

    # 显示选项或自由输入
    if current_options:
        $ quick_menu = False
        call screen story_choice(current_options)
        $ player_input = _return
        $ quick_menu = True
    else:
        $ player_input = renpy.input("你想怎么做？", length=120)

    # 空输入保护
    if not player_input or not player_input.strip():
        $ player_input = "继续观察周围的情况"

    $ player_input = sanitize_player_text(player_input, 120, "继续观察周围的情况")

    jump ai_continue


# ============================================================
# 故事继续生成（单请求、完整验证后提交）
# ============================================================

label ai_continue:

    $ game.continue_story_stream(player_input)

    # 等待首个段落就绪
    call screen loading_animation

    if game.ai_notice:
        $ renpy.notify(game.ai_notice)
        $ game.ai_notice = ""

    # 流式渲染段落
    python:
        while not game.is_stream_complete():
            if game.has_pending_segments():
                seg = game.pop_segment()
                render_stream_segment(seg)
            else:
                renpy.pause(0.2, hard=True)

    # 流式完成
    $ game.finalize_stream_response()

    # 检查剧终
    if game.ended:
        jump story_end

    # 提取下一轮选项
    $ current_options = extract_options(game._full_response)

    jump player_turn


# ============================================================
# 故事结束 + 评价
# ============================================================

label story_end:

    $ quick_menu = False

    # 显示延迟的属性变化弹窗（如有）
    if game._pending_stat_popup:
        call screen stats_change_popup(changes=game._pending_stat_popup)
        $ game._pending_stat_popup = None

    # 取消预生成
    $ game.cancel_prefetch()

    # 隐藏游戏中叠加层
    hide screen stats_overlay
    hide screen encyclopedia_hint
    hide screen character_portrait
    hide screen scene_knowledge_overlay

    "【剧终】"
    "冒险结束了！让我们来看看你的表现吧..."

    # 本地评价始终可用；只有玩家本次开启云端时才请求受控服务。
    $ game.get_evaluation_async()

    call screen loading_animation

    # 格式化评价文本
    if game.ai_result:
        $ eval_text = markdown_to_renpy(game.ai_result)
        $ _raw_eval = game.ai_result
    else:
        $ _raw_eval = build_local_evaluation(game)
        $ eval_text = markdown_to_renpy(_raw_eval)

    # 提取分数和结局信息
    $ _score = extract_score_from_eval(_raw_eval)
    if _score <= 0:
        $ _score = _local_score(game)
    $ _ending_info = extract_ending_info(_raw_eval)

    # 更新游戏统计并存储结局
    python:
        import time as _time_mod
        _run_was_committed = False
        if persistent.current_user:
            _account = get_current_account()
            _committed = _account.setdefault("committed_runs", []) if _account else []
            if game.run_id not in _committed and not any(e.get("run_id") == game.run_id for e in _account.get("endings_unlocked", []) if isinstance(e, dict)):
                _run_was_committed = True
                _committed.append(game.run_id)
                if len(_committed) > 200:
                    del _committed[:-200]
                _ps = get_play_stats()
                _ps["total_plays"] = _ps.get("total_plays", 0) + 1
                _ps["highest_score"] = max(_ps.get("highest_score", 0), _score)
                if game.character:
                    _chars_used = _ps.get("characters_used", [])
                    if game.character not in _chars_used:
                        _chars_used.append(game.character)
                        _ps["characters_used"] = _chars_used
                    _char_counts = _ps.get("character_play_counts", {})
                    _char_counts[game.character] = _char_counts.get(game.character, 0) + 1
                    _ps["character_play_counts"] = _char_counts
                get_endings_unlocked().append({
                    "run_id": game.run_id,
                    "title": _ending_info.get("title", "") or "狗熊岭的新发现",
                    "ending_type": _ending_info.get("ending_type", "") or "温馨成长",
                    "summary": _ending_info.get("summary", "") or "你和伙伴一起完成了这次冒险。",
                    "score": _score,
                    "character": game.character or "",
                    "scenario": game.scenario or "",
                    "date": _time_mod.strftime("%Y-%m-%d"),
                })
                renpy.save_persistent()

    # 检查并解锁新勋章
    $ _new_badges = check_and_unlock_badges(game, _score) if _run_was_committed else []
    if _new_badges:
        call screen badge_unlock_popup(badges=_new_badges)

    jump story_end_eval


# ============================================================
# 评价展示 + 家长报告入口
# ============================================================

label story_end_eval:

    call screen evaluation_screen(eval_text)

    if _return == "restart":
        jump start
    elif _return == "parent_report":
        # 异步生成家长报告
        $ game.get_parent_report_async()
        call screen loading_animation

        if game.parent_report_result:
            call screen parent_report_screen(report_text=game.parent_report_result)

            if _return == "save":
                python:
                    import time as _time_mod2
                    if persistent.current_user:
                        _reports = get_parent_reports()
                        if not any(r.get("run_id") == game.run_id for r in _reports if isinstance(r, dict)):
                            _reports.append({
                                "run_id": game.run_id,
                                "character": game.character or "",
                                "scenario": game.scenario or "",
                                "score": _score,
                                "date": _time_mod2.strftime("%Y-%m-%d"),
                                "report_text": game.parent_report_result,
                            })
                            renpy.save_persistent()
                "报告已保存！可在主菜单「家长报告」中查看。"
        else:
            "报告生成失败，请稍后重试。"

        jump story_end_eval
    else:
        return
