# 熊出没奇遇 — 自定义游戏界面
# 5 个核心 screen + ATL transform + 样式定义

# ============================================================
# ATL Transform 动画
# ============================================================

transform honey_bounce:
    anchor (0.5, 0.5)
    ease 0.6 yoffset -30
    ease 0.6 yoffset 0
    repeat

transform honey_bounce_big:
    anchor (0.5, 0.5)
    ease 0.3 yoffset -50 zoom 1.15
    ease 0.3 yoffset 0 zoom 1.0

transform card_hover:
    on idle:
        ease 0.15 zoom 1.0
    on hover:
        ease 0.15 zoom 1.08

transform fade_in_up:
    alpha 0.0 yoffset 50
    ease 0.3 alpha 1.0 yoffset 0

transform dot_pulse_1:
    alpha 0.3
    linear 0.4 alpha 1.0
    linear 0.4 alpha 0.3
    repeat

transform dot_pulse_2:
    alpha 0.3
    pause 0.15
    linear 0.4 alpha 1.0
    linear 0.4 alpha 0.3
    repeat

transform dot_pulse_3:
    alpha 0.3
    pause 0.3
    linear 0.4 alpha 1.0
    linear 0.4 alpha 0.3
    repeat

transform float_gentle:
    yoffset 0
    ease 1.5 yoffset -10
    ease 1.5 yoffset 0
    repeat

transform avatar_fade_in:
    alpha 0.0 zoom 0.8
    ease 0.4 alpha 1.0 zoom 1.0

transform avatar_fade_out:
    alpha 1.0 zoom 1.0
    ease 0.4 alpha 0.0 zoom 0.8

transform progress_bar_fill:
    xsize 0
    linear 3.0 xsize 490
    linear 12.0 xsize 630

# ============================================================
# ATL Transform — 角色肖像情感动画
# ============================================================

transform sprite_idle:
    yoffset 0
    ease 2.0 yoffset -8
    ease 2.0 yoffset 0
    repeat

transform sprite_happy:
    yoffset 0 zoom 1.0
    ease 0.3 yoffset -20 zoom 1.05
    ease 0.3 yoffset 0 zoom 1.0
    ease 0.3 yoffset -20 zoom 1.05
    ease 0.3 yoffset 0 zoom 1.0
    ease 0.3 yoffset -15 zoom 1.03
    ease 0.3 yoffset 0 zoom 1.0
    yoffset 0
    ease 2.0 yoffset -8
    ease 2.0 yoffset 0
    repeat

transform sprite_angry:
    zoom 1.08
    linear 0.05 xoffset 5
    linear 0.05 xoffset -5
    linear 0.05 xoffset 5
    linear 0.05 xoffset -5
    linear 0.05 xoffset 5
    linear 0.05 xoffset -5
    linear 0.05 xoffset 3
    linear 0.05 xoffset -3
    linear 0.05 xoffset 0
    zoom 1.04
    ease 2.0 yoffset -8
    ease 2.0 yoffset 0
    repeat

transform sprite_scared:
    zoom 0.92
    linear 0.04 xoffset 10 yoffset -5
    linear 0.04 xoffset -10 yoffset 5
    linear 0.04 xoffset 8 yoffset -3
    linear 0.04 xoffset -8 yoffset 3
    linear 0.04 xoffset 10 yoffset -5
    linear 0.04 xoffset -10 yoffset 5
    linear 0.04 xoffset 6 yoffset -2
    linear 0.04 xoffset -6 yoffset 2
    linear 0.04 xoffset 0 yoffset 0
    zoom 0.95
    ease 2.0 yoffset -5
    ease 2.0 yoffset 0
    repeat

transform sprite_surprised:
    yoffset 0 zoom 1.0
    ease 0.15 yoffset -40 zoom 1.15
    ease 0.4 yoffset 0 zoom 1.0
    ease 2.0 yoffset -8
    ease 2.0 yoffset 0
    repeat

transform sprite_sad:
    ease 0.5 yoffset 15 alpha 0.85
    ease 3.0 yoffset 12
    ease 3.0 yoffset 15
    repeat

transform sprite_thinking:
    ease 1.0 rotate 3
    ease 1.0 rotate -3
    repeat

transform sprite_proud:
    ease 0.4 yoffset -15 zoom 1.1
    ease 2.0 yoffset -18
    ease 2.0 yoffset -15
    repeat

transform sprite_nervous:
    linear 0.08 xoffset 3
    linear 0.08 xoffset -3
    repeat

transform sprite_enter:
    alpha 0.0 zoom 0.5 yoffset 50
    ease 0.5 alpha 1.0 zoom 1.0 yoffset 0

transform sprite_exit:
    alpha 1.0 zoom 1.0 yoffset 0
    ease 0.3 alpha 0.0 zoom 0.5 yoffset 50

# ============================================================
# ATL Transform — Side Image 情感动画（120x120 小头像专用）
# ============================================================

transform side_idle:
    yoffset 0
    ease 1.5 yoffset -4
    ease 1.5 yoffset 0
    repeat

transform side_happy:
    yoffset 0 zoom 1.0
    ease 0.2 yoffset -10 zoom 1.08
    ease 0.2 yoffset 0 zoom 1.0
    ease 0.2 yoffset -8 zoom 1.05
    ease 0.2 yoffset 0 zoom 1.0
    ease 1.5 yoffset -4
    ease 1.5 yoffset 0
    repeat

transform side_angry:
    zoom 1.05
    linear 0.04 xoffset 3
    linear 0.04 xoffset -3
    linear 0.04 xoffset 3
    linear 0.04 xoffset -3
    linear 0.04 xoffset 0
    zoom 1.02
    ease 1.5 yoffset -4
    ease 1.5 yoffset 0
    repeat

transform side_scared:
    zoom 0.95
    linear 0.03 xoffset 4 yoffset -2
    linear 0.03 xoffset -4 yoffset 2
    linear 0.03 xoffset 3 yoffset -1
    linear 0.03 xoffset -3 yoffset 1
    linear 0.03 xoffset 0 yoffset 0
    zoom 0.97
    ease 1.5 yoffset -3
    ease 1.5 yoffset 0
    repeat

transform side_surprised:
    yoffset 0 zoom 1.0
    ease 0.12 yoffset -15 zoom 1.1
    ease 0.3 yoffset 0 zoom 1.0
    ease 1.5 yoffset -4
    ease 1.5 yoffset 0
    repeat

transform side_sad:
    ease 0.4 yoffset 6 alpha 0.85
    ease 2.0 yoffset 5
    ease 2.0 yoffset 6
    repeat

transform side_thinking:
    ease 0.8 rotate 2
    ease 0.8 rotate -2
    repeat

transform side_proud:
    ease 0.3 yoffset -8 zoom 1.06
    ease 1.5 yoffset -10
    ease 1.5 yoffset -8
    repeat

transform side_nervous:
    linear 0.06 xoffset 2
    linear 0.06 xoffset -2
    repeat

# ============================================================
# Screen: 角色肖像叠加层（对话时显示）
# ============================================================

screen character_portrait(char_name, emotion=None):

    zorder 50

    $ _char_info = CHARACTERS.get(char_name, {})
    $ _char_color = _char_info.get("color", "#FFFFFF")
    $ _char_avatar = _char_info.get("sprite", _char_info.get("avatar", ""))
    $ _emotion_transform = EMOTION_TRANSFORM_MAP.get(emotion, "sprite_idle")

    frame:
        xalign 0.08 yalign 0.3
        xsize 320 ysize 380
        padding (20, 20)
        background Solid(_char_color + "33")

        vbox:
            xalign 0.5
            spacing 10

            # 角色头像 280x280 + 情感动画
            fixed:
                xsize 280 ysize 280
                xalign 0.5

                # 彩色光晕背景
                add Solid(_char_color + "22"):
                    xalign 0.5 yalign 0.5
                    xsize 270 ysize 270

                if _emotion_transform == "sprite_happy":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_happy
                elif _emotion_transform == "sprite_angry":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_angry
                elif _emotion_transform == "sprite_scared":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_scared
                elif _emotion_transform == "sprite_surprised":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_surprised
                elif _emotion_transform == "sprite_sad":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_sad
                elif _emotion_transform == "sprite_thinking":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_thinking
                elif _emotion_transform == "sprite_proud":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_proud
                elif _emotion_transform == "sprite_nervous":
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_nervous
                else:
                    add Transform(_char_avatar, size=(280, 280), fit="contain"):
                        xalign 0.5 yalign 0.5
                        at sprite_idle

            # 角色名
            text char_name:
                xalign 0.5
                size 28
                color _char_color
                bold True
                outlines [(2, "#000000", 0, 0)]


# ============================================================
# Screen: 口头禅弹出
# ============================================================

# ============================================================
# Screen 1: 角色选择界面
# ============================================================

screen character_select():

    tag menu
    modal True
    zorder 150

    add Transform("bg/bg_forest.webp", xysize=(1920, 1080), fit="cover")
    add Solid("#1a0f05AA")

    frame:
        style "character_select_frame"
        xfill True yfill True

        vbox:
            xalign 0.5 yalign 0.5
            spacing 30

            text "选择你要扮演的角色" style "screen_title"

            textbutton "← 返回主菜单":
                xalign 0.0
                style "settings_btn_small"
                action Return(None)

            grid 3 3:
                xalign 0.5
                spacing 20

                for char_name in ["光头强", "熊大", "熊二", "吉吉国王", "毛毛", "赵琳", "天才威", "大马猴", "二狗"]:
                    button:
                        style "character_card"
                        action Return(char_name)
                        at card_hover

                        vbox:
                            spacing 4
                            xalign 0.5

                            add CHARACTERS[char_name]["avatar"] at Transform(size=(108, 108), fit="contain") xalign 0.5

                            text char_name:
                                xalign 0.5
                                size 26
                                color CHARACTERS[char_name]["color"]
                                bold True
                                outlines [(3, "#FFF4D6", 0, 0), (1, "#14251C", 1, 1)]

                            text CHARACTERS[char_name]["description"]:
                                xalign 0.5
                                size 15
                                color "#cccccc"
                                text_align 0.5
                                xmaximum 290


# ============================================================
# Screen 2: 游戏设置界面
# ============================================================

screen game_settings():

    tag menu
    modal True
    zorder 150

    default scenario_text = renpy.random.choice(EXAMPLE_SCENARIOS)
    default mode = "小朋友独立体验"
    default difficulty = "儿童难度"
    default duration = 10
    default powerup = ""
    default fate_text = ""
    default ending_type = ""
    default show_fate_input = False
    default tts_enabled = False
    default online_enabled = False

    add Transform("bg/bg_cabin.webp", xysize=(1920, 1080), fit="cover")
    add Solid("#1a0f05CC")

    frame:
        style "settings_frame"
        xalign 0.5 yalign 0.5
        xsize 1280
        ysize 950
        padding (60, 42)

        viewport:
            mousewheel True
            draggable True
            pagekeys True
            scrollbars "vertical"
            yfill True
            vscrollbar_xsize 18
            vscrollbar_base_bar Solid("#31483A")
            vscrollbar_thumb Solid("#F6B73C")
            vscrollbar_hover_thumb Solid("#FFD166")

            vbox:
                spacing 30
                xfill True

                text "冒险设置" style "screen_title"

                textbutton "← 重新选角":
                    style "settings_btn_small"
                    action Return("__back__")

                # --- 情景主题 ---
                vbox:
                    spacing 10
                    xfill True
                    text "情景主题" size 28 color "#FFD700" bold True

                    hbox:
                        spacing 15
                        xfill True

                        frame:
                            xfill True
                            padding (15, 10)
                            background Solid("#4a3520")
                            input:
                                id "scenario_input"
                                value ScreenVariableInputValue("scenario_text")
                                length 80
                                size 26
                                color "#ffffff"
                                xfill True

                        textbutton "随机":
                            style "settings_btn_small"
                            action SetScreenVariable("scenario_text", renpy.random.choice(EXAMPLE_SCENARIOS))

                # --- 体验模式 ---
                vbox:
                    spacing 10
                    text "体验模式" size 28 color "#FFD700" bold True
                    hbox:
                        spacing 15
                        textbutton "小朋友独立体验":
                            style "settings_toggle"
                            selected (mode == "小朋友独立体验")
                            action SetScreenVariable("mode", "小朋友独立体验")
                        textbutton "亲子共玩":
                            style "settings_toggle"
                            selected (mode == "亲子共玩")
                            action SetScreenVariable("mode", "亲子共玩")

                # --- 难度 ---
                vbox:
                    spacing 10
                    text "难度" size 28 color "#FFD700" bold True
                    hbox:
                        spacing 15
                        textbutton "儿童难度":
                            style "settings_toggle"
                            selected (difficulty == "儿童难度")
                            action SetScreenVariable("difficulty", "儿童难度")
                        textbutton "青少年难度":
                            style "settings_toggle"
                            selected (difficulty == "青少年难度")
                            action SetScreenVariable("difficulty", "青少年难度")

                # --- 时长 ---
                vbox:
                    spacing 10
                    text "体验时长（分钟）" size 28 color "#FFD700" bold True
                    hbox:
                        spacing 15
                        for dur in [5, 10, 15, 20]:
                            textbutton "[dur]":
                                style "settings_toggle"
                                selected (duration == dur)
                                action SetScreenVariable("duration", dur)

                # --- 蜂蜜罐神器 ---
                vbox:
                    spacing 10
                    hbox:
                        spacing 10
                        add "honey_jar.webp" at Transform(size=(36, 36))
                        text "蜂蜜罐神器" size 28 color "#FFD700" bold True

                    hbox:
                        spacing 15
                        textbutton "不使用":
                            style "settings_toggle"
                            selected (powerup == "")
                            action [SetScreenVariable("powerup", ""), SetScreenVariable("show_fate_input", False)]
                        textbutton "问题提示":
                            style "settings_toggle"
                            selected (powerup == "问题提示神器")
                            action [SetScreenVariable("powerup", "问题提示神器"), SetScreenVariable("show_fate_input", False)]
                        textbutton "命运改写":
                            style "settings_toggle"
                            selected (powerup == "人物命运改写神器")
                            action [SetScreenVariable("powerup", "人物命运改写神器"), SetScreenVariable("show_fate_input", True)]
                        textbutton "结局指定":
                            style "settings_toggle"
                            selected (powerup == "结局指定神器")
                            action [SetScreenVariable("powerup", "结局指定神器"), SetScreenVariable("show_fate_input", False)]

                    # 命运改写输入
                    if powerup == "人物命运改写神器":
                        hbox:
                            spacing 10
                            text "指定命运：" size 24 color "#aaaaaa" yalign 0.5
                            frame:
                                xsize 600
                                padding (15, 10)
                                background Solid("#4a3520")
                                input:
                                    value ScreenVariableInputValue("fate_text")
                                    length 60
                                    size 24
                                    color "#ffffff"

                    # 结局指定选择
                    if powerup == "结局指定神器":
                        hbox:
                            spacing 15
                            for etype in ["大团圆式结局", "意料之外结局", "留白式结局"]:
                                textbutton etype:
                                    style "settings_toggle"
                                    selected (ending_type == etype)
                                    action SetScreenVariable("ending_type", etype)

                # --- 故事引擎与隐私 ---
                vbox:
                    spacing 10
                    text "故事引擎" size 28 color "#F6B73C" bold True
                    hbox:
                        spacing 15
                        textbutton "本地故事 ✓":
                            style "settings_toggle"
                            selected (online_enabled == False)
                            action SetScreenVariable("online_enabled", False)
                        textbutton "云端动态故事":
                            style "settings_toggle"
                            selected (online_enabled == True)
                            sensitive ai_service_configured()
                            action SetScreenVariable("online_enabled", True)
                    if ai_service_configured():
                        text "云端模式会把本次情景、选择和报告素材发送到已配置服务。请由监护人确认后开启。" size 18 color "#FFF4D6"
                    else:
                        text "当前发行版仅使用本地故事，无需联网也能完整通关。" size 18 color "#BFD8C4"

                # --- 朗读模式 ---
                vbox:
                    spacing 10
                    text "朗读模式" size 28 color "#FFD700" bold True
                    hbox:
                        spacing 15
                        textbutton "关闭":
                            style "settings_toggle"
                            selected (tts_enabled == False)
                            action SetScreenVariable("tts_enabled", False)
                        textbutton "开启":
                            style "settings_toggle"
                            selected (tts_enabled == True)
                            action SetScreenVariable("tts_enabled", True)
                    text "使用设备自带的系统朗读，不需联网。" size 18 color "#BFD8C4"

                # --- 开始按钮 ---
                null height 20
                textbutton "开始冒险！":
                    style "start_adventure_btn"
                    xalign 0.5
                    sensitive bool(scenario_text.strip()) and (powerup != "人物命运改写神器" or bool(fate_text.strip())) and (powerup != "结局指定神器" or bool(ending_type))
                    action Return({
                        "scenario": scenario_text,
                        "mode": mode,
                        "difficulty": difficulty,
                        "duration": duration,
                        "powerup": powerup,
                        "fate_text": fate_text,
                        "ending_type": ending_type,
                        "tts_enabled": tts_enabled,
                        "online_enabled": online_enabled,
                    })

                if not scenario_text.strip():
                    text "请先填写一个情景主题。" size 18 color "#FFB4A9" xalign 0.5
                elif powerup == "人物命运改写神器" and not fate_text.strip():
                    text "请先写下你想指定的人物命运。" size 18 color "#FFB4A9" xalign 0.5
                elif powerup == "结局指定神器" and not ending_type:
                    text "请先选择一种结局类型。" size 18 color "#FFB4A9" xalign 0.5


# ============================================================
# Screen 3: 加载动画（增强版）
# ============================================================

screen loading_animation():

    modal True
    zorder 200

    # 森林主题半透明背景
    add Transform("bg/bg_forest.webp", xysize=(1920, 1080), fit="cover")
    add Solid("#1a0f05CC")

    # 角色名列表用于轮播
    default _avatar_names = list(CHARACTERS.keys())
    default tip_index = 0
    default avatar_index = 0
    default honey_clicked = False
    default fun_fact = ""

    # 趣味点击提示
    python:
        _fun_facts = [
            "你知道吗？熊二一天能吃20罐蜂蜜！",
            "光头强的电锯其实是从网上买的！",
            "吉吉国王的王冠是用树叶做的！",
            "毛毛是狗熊岭跑得最快的猴子！",
            "天才威的发明成功率只有1%！",
        ]

    vbox:
        xalign 0.5 yalign 0.45
        spacing 20

        # 角色头像轮播
        fixed:
            xsize 140 ysize 140
            xalign 0.5

            $ _cur_avatar_name = _avatar_names[avatar_index % len(_avatar_names)]
            $ _cur_avatar_path = CHARACTERS[_cur_avatar_name]["avatar"]
            $ _cur_avatar_color = CHARACTERS[_cur_avatar_name]["color"]

            add Transform(_cur_avatar_path, size=(130, 130), fit="contain"):
                xalign 0.5 yalign 0.5
                at avatar_fade_in

        # 角色名字
        text _cur_avatar_name:
            xalign 0.5
            size 24
            color _cur_avatar_color
            bold True

        null height 5

        # 蜂蜜罐（可点击互动）
        button:
            xalign 0.5
            action [SetScreenVariable("honey_clicked", True),
                    SetScreenVariable("fun_fact", renpy.random.choice(_fun_facts))]

            if honey_clicked:
                add "honey_jar.webp" at honey_bounce_big xalign 0.5 zoom 1.8
            else:
                add "honey_jar.webp" at float_gentle xalign 0.5 zoom 1.8

        # 趣味提示（点击蜂蜜罐后显示）
        if honey_clicked and fun_fact:
            text fun_fact:
                xalign 0.5
                size 22
                color "#FFB347"
                italic True

        null height 5

        # "AI导演正在创作故事" + 脉冲点
        hbox:
            xalign 0.5
            spacing 0
            text ("云端导演正在编排冒险" if game.online_enabled else "本地导演正在编排冒险") size 30 color "#F6B73C"
            text " ." size 30 color "#FFD700" at dot_pulse_1
            text "." size 30 color "#FFD700" at dot_pulse_2
            text "." size 30 color "#FFD700" at dot_pulse_3

        # 伪进度条
        frame:
            xalign 0.5
            xsize 700
            ysize 12
            background Solid("#4a3520")
            padding (0, 0)

            frame:
                ysize 12
                background Solid("#FFD700")
                at progress_bar_fill
                padding (0, 0)

        # 轮播提示文字
        text LOADING_TIPS[tip_index % len(LOADING_TIPS)]:
            xalign 0.5
            size 24
            color "#aaaaaa"
            italic True

    # 每 3 秒切换角色和提示
    timer 3.0 repeat True action [
        SetScreenVariable("tip_index", tip_index + 1),
        SetScreenVariable("avatar_index", avatar_index + 1),
        SetScreenVariable("honey_clicked", False),
        SetScreenVariable("fun_fact", ""),
    ]

    # 退出条件：段落就绪 OR AI 不忙了
    timer 0.15 repeat True action If(
        game.has_pending_segments() or (not game.ai_busy),
        true=Return()
    )


# ============================================================
# Screen 4: 故事选项界面
# ============================================================

screen story_choice(options):

    modal True
    zorder 100

    default show_input = False
    default custom_text = ""

    frame:
        xalign 0.5 yalign 1.0
        xsize 1500
        yminimum 200
        padding (40, 30)
        background Solid("#14251CF2")

        vbox:
            spacing 15
            xfill True

            text "你想怎么做？" size 30 color "#FFD700" bold True xalign 0.5

            if len(options) > 0 and not show_input:
                for i, opt in enumerate(options):
                    $ opt_letter = opt[0]
                    $ opt_content = opt[1]
                    $ btn_colors = ["#2F6B3F", "#446B4C", "#5A4B2B"]
                    $ btn_hover_colors = ["#3D8551", "#56855F", "#756338"]
                    $ btn_color = btn_colors[i] if i < len(btn_colors) else "#2F6B3F"
                    $ btn_hover = btn_hover_colors[i] if i < len(btn_hover_colors) else "#3D8551"
                    textbutton "[opt_letter]. [opt_content]":
                        xfill True
                        padding (25, 18)
                        background Solid(btn_color)
                        hover_background Solid(btn_hover)
                        text_size 28
                        text_color "#ffffff"
                        action Return(opt_letter + ". " + opt_content)

                textbutton "我有自己的想法...":
                    xalign 0.5
                    padding (20, 12)
                    text_size 24
                    text_color "#aaaaaa"
                    action SetScreenVariable("show_input", True)

            if show_input or len(options) == 0:
                hbox:
                    spacing 15
                    xfill True

                    frame:
                        xfill True
                        padding (15, 12)
                        background Solid("#4a3520")
                        input:
                            id "custom_input"
                            value ScreenVariableInputValue("custom_text")
                            length 120
                            size 26
                            color "#ffffff"
                            xfill True

                    textbutton "确定":
                        padding (25, 12)
                        text_size 26
                        text_color "#FFD700"
                        action If(custom_text.strip(), true=Return(custom_text.strip()), false=NullAction())

                if len(options) > 0:
                    textbutton "返回选项":
                        xalign 0.5
                        text_size 22
                        text_color "#aaaaaa"
                        action SetScreenVariable("show_input", False)


# ============================================================
# Screen 5: 评价界面
# ============================================================

screen evaluation_screen(eval_text):

    tag menu
    modal True
    zorder 150

    add Solid("#2d1b0eFF")

    frame:
        xalign 0.5 yalign 0.5
        xsize 1400
        ysize 900
        padding (60, 50)
        background Solid("#3e2a15EE")

        vbox:
            spacing 25
            xfill True yfill True

            text "冒险总结" style "screen_title"

            viewport:
                xfill True
                yfill True
                mousewheel True
                draggable True
                pagekeys True
                scrollbars "vertical"

                text eval_text:
                    size 26
                    color "#dddddd"
                    line_spacing 8

            hbox:
                xalign 0.5
                spacing 40

                textbutton "再来一次":
                    padding (40, 18)
                    text_size 30
                    text_color "#2ecc71"
                    action Return("restart")

                textbutton "生成家长报告":
                    padding (40, 18)
                    text_size 30
                    text_color "#3498db"
                    action Return("parent_report")

                textbutton "返回主菜单":
                    padding (40, 18)
                    text_size 30
                    text_color "#e67e22"
                    action Return("main_menu")


# ============================================================
# 错误/重试界面
# ============================================================

screen ai_error_screen(error_msg):

    modal True
    zorder 200

    add Solid("#1a0f0599")

    frame:
        xalign 0.5 yalign 0.5
        xsize 800
        padding (50, 40)
        background Solid("#3e2a15FF")

        vbox:
            spacing 20
            xfill True

            text "哎呀，故事暂停了一下" size 32 color "#F6B73C" bold True xalign 0.5

            text "你可以重试，或先返回主菜单。技术详情已记录，不会在小朋友的界面中展示。":
                size 22
                color "#D6C9A3"
                xalign 0.5
                text_align 0.5

            hbox:
                xalign 0.5
                spacing 30

                textbutton "重试":
                    padding (30, 15)
                    text_size 28
                    text_color "#2ecc71"
                    action Return("retry")

                textbutton "返回主菜单":
                    padding (30, 15)
                    text_size 28
                    text_color "#e67e22"
                    action Return("main_menu")


# ============================================================
# 自定义样式
# ============================================================

style screen_title is default:
    font "ZCOOLKuaiLe-Regular.ttf"
    size 42
    color "#F6B73C"
    bold True
    xalign 0.5
    text_align 0.5

style character_select_frame is frame:
    background None

style character_card is button:
    xsize 340
    ysize 220
    padding (16, 12)
    background Solid("#203B2BEE")
    hover_background Solid("#315B3FFF")

style settings_frame is frame:
    background Solid("#14251CF2")

style settings_toggle is button:
    padding (20, 12)
    background Solid("#213B2CEE")
    hover_background Solid("#315B3FFF")
    selected_background Solid("#F6B73C")
    insensitive_background Solid("#28342DDD")

style settings_toggle_text is button_text:
    size 24
    color "#888888"
    selected_color "#14251C"
    insensitive_color "#7F8B82"

style settings_btn_small is button:
    padding (20, 10)

style settings_btn_small_text is button_text:
    size 24
    color "#FFD700"

style start_adventure_btn is button:
    padding (60, 20)
    background Solid("#F6B73C")
    hover_background Solid("#FFD166")
    insensitive_background Solid("#5B625CDD")

style start_adventure_btn_text is button_text:
    size 36
    color "#14251C"
    insensitive_color "#A8ADA9"
    bold True


# ============================================================
# ATL Transform — 新增动画（四维属性、情商、百科、QTE）
# ============================================================

transform stat_change_float:
    alpha 1.0 yoffset 0
    linear 1.5 alpha 0.0 yoffset -40

transform stat_change_center_popup:
    alpha 0.0 zoom 0.6 yoffset 20
    ease 0.2 alpha 1.0 zoom 1.1 yoffset 0
    ease 0.1 zoom 1.0
    pause 0.8
    ease 0.5 alpha 0.0 yoffset -60

transform encyclopedia_pulse:
    alpha 0.6 zoom 1.0
    ease 0.8 alpha 1.0 zoom 1.1
    ease 0.8 alpha 0.6 zoom 1.0
    repeat

transform qte_pulse_border:
    alpha 0.3
    linear 0.3 alpha 0.8
    linear 0.3 alpha 0.3
    repeat

transform qte_button_bounce:
    zoom 1.0
    ease 0.08 zoom 0.9
    ease 0.08 zoom 1.0

transform badge_shine:
    zoom 0.5 alpha 0.0
    ease 0.4 zoom 1.2 alpha 1.0
    ease 0.2 zoom 1.0

transform qte_countdown_bar(secs):
    xsize 600
    linear secs xsize 0

transform grayscale_fade_in:
    matrixcolor IdentityMatrix()
    linear 0.5 matrixcolor SaturationMatrix(0.0)

transform grayscale_fade_out:
    matrixcolor SaturationMatrix(0.0)
    linear 0.5 matrixcolor IdentityMatrix()


# ============================================================
# Screen: 四维属性常驻侧边栏
# ============================================================

screen stats_overlay():

    zorder 30

    frame:
        xalign 0.98 yalign 0.03
        xsize 240
        padding (18, 14)
        background Frame(Solid("#3d2215EE"), 4, 4)

        vbox:
            spacing 8

            for _stat_name in STAT_NAMES:
                $ _stat_val = game.stats.get(_stat_name, 5)
                $ _stat_color = STAT_COLORS.get(_stat_name, "#ffffff")
                hbox:
                    spacing 8
                    text _stat_name:
                        size 26
                        bold True
                        color _stat_color
                        outlines [(2, "#00000088", 0, 0)]
                        min_width 30
                    bar:
                        value _stat_val
                        range 10
                        xsize 120
                        ysize 18
                        yalign 0.5
                        left_bar Solid(_stat_color)
                        right_bar Solid("#6b4a30")
                    text "[_stat_val]":
                        size 22
                        bold True
                        color "#FFD700"
                        outlines [(1, "#00000088", 0, 0)]
                        min_width 30


# ============================================================
# Screen: 属性变化弹窗
# ============================================================

screen stats_change_popup(changes):

    modal True
    zorder 180

    add Solid("#14251C88")

    frame:
        at stat_change_center_popup
        xalign 0.5 yalign 0.35
        xminimum 300
        padding (24, 18)
        background Frame(Solid("#3d2215EE"), 4, 4)

        vbox:
            spacing 8
            text "属性变化":
                size 32
                bold True
                color "#FFD700"
                xalign 0.5
                outlines [(2, "#00000088", 0, 0)]
            null height 4
            for _dim, _delta in changes.items():
                if _delta != 0:
                    $ _arrow = "\u2191" if _delta > 0 else "\u2193"
                    $ _sign = "+" if _delta > 0 else ""
                    $ _col = "#2ecc71" if _delta > 0 else "#e74c3c"
                    text "{} {} {}{}".format(_dim, _arrow, _sign, _delta):
                        size 38
                        bold True
                        color _col
                        xalign 0.5
                        outlines [(2, "#00000088", 0, 0)]

            textbutton "知道了":
                xalign 0.5
                padding (28, 12)
                text_size 24
                text_color "#14251C"
                background Solid("#F6B73C")
                hover_background Solid("#FFD166")
                action Return()


# ============================================================
# Screen: 保存并退出确认
# ============================================================

screen confirm_save_and_quit():

    modal True
    zorder 200

    add Solid("#1a0f05AA")

    frame:
        xalign 0.5 yalign 0.45
        xsize 800
        padding (50, 40)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xalign 0.5

            text "小朋友，要保存一下现在的进度吗？":
                size 36
                color "#FFF8E1"
                xalign 0.5
                text_align 0.5
                outlines [(2, "#00000088", 0, 0)]

            null height 10

            hbox:
                spacing 30
                xalign 0.5

                textbutton "保存并返回":
                    sensitive bool(get_current_account()) and story_state_is_stable()
                    action FileSave(
                        get_account_quick_slot(),
                        page=get_account_quick_page(),
                        confirm=False,
                        action=MainMenu(confirm=False)
                    )
                    text_size 30
                    text_color "#2ecc71"
                    text_hover_color "#27ae60"

                textbutton "直接返回":
                    action MainMenu(confirm=False)
                    text_size 30
                    text_color "#e67e22"
                    text_hover_color "#d35400"

                textbutton "取消":
                    action Hide("confirm_save_and_quit")
                    text_size 30
                    text_color "#95a5a6"
                    text_hover_color "#7f8c8d"

    key "game_menu" action Hide("confirm_save_and_quit")


# ============================================================
# Screen: 情商反馈（内心世界）
# ============================================================

screen eq_feedback_screen(reflection=""):

    modal True
    zorder 180

    # 灰度背景覆盖
    add Solid("#1a0f05AA")

    frame:
        xalign 0.5 yalign 0.45
        xsize 1000
        ysize 500
        padding (50, 40)
        background Solid("#3e2a15EE")

        hbox:
            spacing 40
            yalign 0.5

            # 熊大头像
            frame:
                background Solid("#8B451333")
                padding (10, 10)
                add Transform("avatars/xiongda.png", size=(200, 200))

            vbox:
                spacing 25
                yalign 0.5
                xsize 620

                text "熊大想对你说……" size 28 color "#F6B73C" bold True

                text reflection:
                    size 24
                    color "#dddddd"
                    line_spacing 8

                textbutton "我明白了":
                    xalign 0.5
                    padding (40, 15)
                    text_size 26
                    text_color "#FFD700"
                    action Return()


# ============================================================
# Screen: 百科侧边栏提示图标
# ============================================================

screen encyclopedia_hint():

    zorder 60

    if game._pending_encyclopedia:
        $ _enc_item = game._pending_encyclopedia[0]

        button:
            xalign 0.97 yalign 0.5
            xsize 96 ysize 72
            background Solid("#2ecc7188")
            hover_background Solid("#2ecc71CC")
            at encyclopedia_pulse
            alt "打开百科知识：[_enc_item['name']]"
            action Show("encyclopedia_card", enc_name=_enc_item["name"], enc_desc=_enc_item["description"])

            text "百科" size 22 color "#ffffff" xalign 0.5 yalign 0.5 bold True


# ============================================================
# Screen: 百科知识卡片
# ============================================================

screen encyclopedia_card(enc_name="", enc_desc=""):

    modal True
    zorder 170

    add Solid("#1a0f0588")

    frame:
        xalign 0.5 yalign 0.5
        xsize 650
        ysize 420
        padding (40, 35)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xfill True

            text "森林百科" size 22 color "#2ecc71" xalign 0.5

            text enc_name size 36 color "#FFD700" bold True xalign 0.5

            null height 5

            text enc_desc:
                size 24
                color "#dddddd"
                line_spacing 8
                text_align 0.5
                xalign 0.5

            null height 10

            hbox:
                xalign 0.5
                spacing 30

                if enc_name in get_forest_notes():
                    textbutton "已收藏 \u2713":
                        padding (25, 12)
                        text_size 22
                        text_color "#888888"
                        action NullAction()
                else:
                    textbutton "收藏到森林笔记":
                        padding (25, 12)
                        text_size 22
                        text_color "#2ecc71"
                        action [SetDict(get_forest_notes(), enc_name, {"description": enc_desc, "date": "", "scenario": game.scenario or ""}), renpy.restart_interaction]

                textbutton "继续冒险":
                    padding (25, 12)
                    text_size 22
                    text_color "#f39c12"
                    action [Hide("encyclopedia_card"), Function(game._pending_encyclopedia.pop, 0)]


# ============================================================
# Screen: 森林笔记（百科画廊 — 主菜单可访问）
# ============================================================

screen forest_notes():

    tag menu

    use game_menu("森林笔记"):

        if not get_forest_notes():
            text "还没有发现任何知识点，快去冒险吧！" size 28 color "#888888" xalign 0.5 yalign 0.4

        else:
            vbox:
                spacing 10
                xfill True

                text "已发现 {} 个知识点".format(len(get_forest_notes())):
                    size 22
                    color "#2ecc71"
                    xalign 0.5

                null height 10

                viewport:
                    xfill True
                    yfill True
                    mousewheel True
                    draggable True
                    pagekeys True
                    scrollbars "vertical"

                    vbox:
                        spacing 12
                        xfill True

                        for _fn_name, _fn_info in sorted(get_forest_notes().items()):
                            frame:
                                xfill True
                                padding (20, 15)
                                background Solid("#3e2a15CC")

                                vbox:
                                    spacing 6
                                    text _fn_name size 26 color "#FFD700" bold True
                                    text _fn_info.get("description", "") size 20 color "#cccccc"
                                    if _fn_info.get("scenario"):
                                        text "发现于：{}".format(_fn_info["scenario"]) size 16 color "#666666"


# ============================================================
# Screen: 结局图鉴
# ============================================================

screen ending_gallery():

    tag menu

    use game_menu("结局图鉴"):

        if not get_endings_unlocked():
            text "还没有完成任何冒险，快去创造故事吧！" size 28 color "#888888" xalign 0.5 yalign 0.4

        else:
            vbox:
                spacing 10
                xfill True

                text "已解锁 {} 个结局".format(len(get_endings_unlocked())):
                    size 22
                    color "#e67e22"
                    xalign 0.5

                null height 10

                viewport:
                    xfill True
                    yfill True
                    mousewheel True
                    draggable True
                    pagekeys True
                    scrollbars "vertical"

                    vbox:
                        spacing 15
                        xfill True

                        for _ending in reversed(list(get_endings_unlocked())):
                            $ _e_char = _ending.get("character", "")
                            $ _e_color = CHARACTERS.get(_e_char, {}).get("color", "#888888")
                            frame:
                                xfill True
                                padding (20, 15)
                                background Solid(_e_color + "33")

                                hbox:
                                    spacing 15
                                    yalign 0.5

                                    # 小头像
                                    $ _e_avatar = CHARACTERS.get(_e_char, {}).get("avatar", "")
                                    if _e_avatar:
                                        add Transform(_e_avatar, size=(50, 50)) yalign 0.5
                                    else:
                                        null width 50

                                    vbox:
                                        spacing 4
                                        text _ending.get("title", "未知结局") size 24 color "#FFD700" bold True
                                        hbox:
                                            spacing 15
                                            text _ending.get("ending_type", "") size 18 color "#aaaaaa"
                                            text "{}/100".format(_ending.get("score", "?")) size 18 color _e_color
                                            text _ending.get("date", "") size 18 color "#666666"
                                        if _ending.get("summary"):
                                            text _ending["summary"] size 18 color "#cccccc"


# ============================================================
# Screen: 勋章墙
# ============================================================

screen badge_gallery():

    tag menu

    use game_menu("勋章墙"):

        vbox:
            spacing 10
            xfill True

            $ _unlocked_count = len(get_badges())
            $ _total_count = len(BADGE_DEFINITIONS)
            text "已获得 {}/{} 枚勋章".format(_unlocked_count, _total_count):
                size 22
                color "#FFD700"
                xalign 0.5

            null height 10

            viewport:
                xfill True
                yfill True
                mousewheel True
                draggable True
                pagekeys True
                scrollbars "vertical"

                $ _grid_rows = (_total_count + 2) // 3
                grid 3 _grid_rows:
                    xalign 0.5
                    spacing 15

                    for _badge_id, _badge_def in BADGE_DEFINITIONS.items():
                        $ _is_unlocked = _badge_id in get_badges()
                        $ _medal_img = _badge_def.get("medal_image", "")
                        frame:
                            xsize 280
                            ysize 200
                            padding (15, 12)
                            if _is_unlocked:
                                background Solid("#3e2a15CC")
                            else:
                                background Solid("#2d1b0e88")

                            vbox:
                                spacing 6
                                xalign 0.5

                                if _is_unlocked:
                                    if _medal_img:
                                        add Transform(_medal_img, xsize=80, ysize=80, fit="contain") xalign 0.5
                                    else:
                                        text _badge_def["icon"] size 42 xalign 0.5 color "#FFD700"
                                    text _badge_def["name"] size 20 xalign 0.5 color "#FFD700" bold True
                                    text _badge_def["description"] size 14 xalign 0.5 color "#cccccc" text_align 0.5
                                    text get_badges()[_badge_id].get("date", "") size 12 xalign 0.5 color "#666666"
                                else:
                                    if _medal_img:
                                        add Transform(_medal_img, xsize=80, ysize=80, fit="contain", matrixcolor=SaturationMatrix(0.0) * BrightnessMatrix(-0.3)) xalign 0.5
                                    else:
                                        text "?" size 42 xalign 0.5 color "#444444"
                                    text _badge_def["name"] size 20 xalign 0.5 color "#555555"
                                    text "???" size 14 xalign 0.5 color "#333333"

                    # 填充空格使 grid 完整
                    for _i in range((3 - _total_count % 3) % 3):
                        null width 280


# ============================================================
# Screen: 勋章解锁弹窗
# ============================================================

screen badge_unlock_popup(badges=None):

    modal True
    zorder 190

    add Solid("#1a0f0599")

    frame:
        xalign 0.5 yalign 0.45
        xsize 600
        padding (40, 35)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xfill True

            text "恭喜获得新勋章！" size 32 color "#FFD700" bold True xalign 0.5

            null height 5

            for _badge in (badges or []):
                hbox:
                    spacing 15
                    xalign 0.5

                    $ _popup_medal_img = _badge.get("medal_image", "")
                    if _popup_medal_img:
                        add Transform(_popup_medal_img, xsize=60, ysize=60, fit="contain") yalign 0.5 at badge_shine
                    else:
                        text _badge.get("icon", "★"):
                            size 36
                            color "#FFD700"
                            at badge_shine

                    vbox:
                        text _badge.get("name", "") size 26 color "#FFD700" bold True
                        text _badge.get("description", "") size 20 color "#cccccc"

            null height 10

            textbutton "太棒了！":
                xalign 0.5
                padding (40, 15)
                text_size 28
                text_color "#2ecc71"
                action Return()


# ============================================================
# Screen: QTE 快速反应挑战
# ============================================================

screen qte_screen(description="挑战！", seconds=5):

    modal True
    zorder 200

    default clicks = 0
    default remaining = seconds
    $ _target = max(4, seconds * 2 if game._game_difficulty == "青少年难度" else seconds + seconds // 2)

    # 紧张红色边框
    add Solid("#2d0a0aEE")

    frame:
        xalign 0.5 yalign 0.5
        xsize 800
        ysize 650
        padding (40, 30)
        background Solid("#3e1a15EE")

        vbox:
            spacing 20
            xfill True

            # 任务描述
            text description size 32 color "#ffffff" bold True xalign 0.5 text_align 0.5

            null height 5

            # 倒计时条
            text "剩余 [remaining] 秒" size 22 color "#FFD166" xalign 0.5
            frame:
                xalign 0.5
                xsize 600
                ysize 20
                background Solid("#4a3520")

                frame:
                    ysize 20
                    background Solid("#e74c3c")
                    at qte_countdown_bar(seconds)

            null height 10

            # 点击按钮
            button:
                xalign 0.5
                xsize 240
                ysize 200
                background Solid("#F6B73C")
                hover_background Solid("#FFD166")
                action SetScreenVariable("clicks", clicks + 1)
                at qte_button_bounce

                vbox:
                    xalign 0.5
                    yalign 0.5
                    text "点击！" size 36 color "#14251C" bold True xalign 0.5
                    text "[clicks]/[_target]" size 24 color "#14251CCC" xalign 0.5

            # 进度条
            bar:
                value clicks
                range _target
                xsize 600
                ysize 16
                xalign 0.5
                left_bar Solid("#2ecc71")
                right_bar Solid("#4a3520")

            text "也可按空格键，或选择轻松完成。" size 18 color "#D6C9A3" xalign 0.5
            textbutton "轻松完成":
                xalign 0.5
                xsize 240
                ysize 56
                padding (24, 10)
                background Solid("#BFD8C4")
                hover_background Solid("#F6B73C")
                text_size 22
                text_color "#14251C"
                text_bold True
                text_xalign 0.5
                action Return("assist")

    key "K_SPACE" action SetScreenVariable("clicks", clicks + 1)
    timer 1.0 repeat True action SetScreenVariable("remaining", max(0, remaining - 1))

    # 成功判定
    if clicks >= _target:
        timer 0.1 action Return("success")

    # 超时判定
    timer seconds action Return("fail")


# ============================================================
# Screen: QTE 结果
# ============================================================

screen qte_result_screen(success=True):

    modal True
    zorder 200

    add Solid("#1a0f0599")

    frame:
        xalign 0.5 yalign 0.45
        xsize 500
        ysize 280
        padding (40, 35)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xalign 0.5
            yalign 0.5

            if success:
                text "挑战成功！" size 42 color "#2ecc71" bold True xalign 0.5
                text "太厉害了！" size 24 color "#dddddd" xalign 0.5
            else:
                text "差一点点！" size 42 color "#e67e22" bold True xalign 0.5
                text "没关系，下次一定行！" size 24 color "#dddddd" xalign 0.5

            textbutton "继续冒险":
                xalign 0.5
                padding (30, 12)
                text_size 24
                text_color "#FFD700"
                action Return()


# ============================================================
# Screen: 家长报告展示
# ============================================================

screen parent_report_screen(report_text=""):

    modal True
    zorder 180

    add Solid("#2d1b0eFF")

    frame:
        xalign 0.5 yalign 0.5
        xsize 1400
        ysize 900
        padding (60, 50)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xfill True yfill True

            text "家长成长报告" size 36 color "#3498db" bold True xalign 0.5

            viewport:
                xfill True
                yfill True
                mousewheel True
                draggable True
                pagekeys True
                scrollbars "vertical"

                text report_text:
                    size 24
                    color "#dddddd"
                    line_spacing 8

            hbox:
                xalign 0.5
                spacing 30

                textbutton "保存报告":
                    padding (30, 15)
                    text_size 26
                    text_color "#2ecc71"
                    action Return("save")

                textbutton "返回":
                    padding (30, 15)
                    text_size 26
                    text_color "#e67e22"
                    action Return("back")


# ============================================================
# Screen: 家长报告历史列表（主菜单可访问）
# ============================================================

screen parent_reports_history():

    tag menu

    use game_menu("家长报告"):

        if not get_parent_reports():
            text "还没有生成任何家长报告。\n完成冒险后可在评价界面生成报告。" size 26 color "#888888" xalign 0.5 yalign 0.4 text_align 0.5

        else:
            viewport:
                xfill True
                yfill True
                mousewheel True
                draggable True
                pagekeys True
                scrollbars "vertical"

                vbox:
                    spacing 12
                    xfill True

                    for _idx, _report in enumerate(reversed(list(get_parent_reports()))):
                        $ _r_char = _report.get("character", "")
                        $ _r_color = CHARACTERS.get(_r_char, {}).get("color", "#888888")
                        button:
                            xfill True
                            padding (20, 15)
                            background Solid("#3e2a15CC")
                            hover_background Solid("#5c3d1fCC")
                            action Show("parent_report_detail", report=_report)

                            hbox:
                                spacing 15
                                yalign 0.5

                                $ _r_avatar = CHARACTERS.get(_r_char, {}).get("avatar", "")
                                if _r_avatar:
                                    add Transform(_r_avatar, size=(40, 40)) yalign 0.5
                                else:
                                    null width 40

                                vbox:
                                    spacing 3
                                    text "{}  {}".format(_report.get("date", ""), _report.get("scenario", "")):
                                        size 22
                                        color "#FFD700"
                                    text "角色：{}  评分：{}/100".format(_r_char, _report.get("score", "?")):
                                        size 18
                                        color "#aaaaaa"


screen parent_report_detail(report=None):

    modal True
    zorder 170

    add Solid("#2d1b0eFF")

    frame:
        xalign 0.5 yalign 0.5
        xsize 1400
        ysize 900
        padding (60, 50)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xfill True yfill True

            $ _pr_date = report.get("date", "") if report else ""
            $ _pr_scenario = report.get("scenario", "") if report else ""
            text "家长报告 — {} {}".format(_pr_date, _pr_scenario):
                size 30
                color "#3498db"
                bold True
                xalign 0.5

            viewport:
                xfill True
                yfill True
                mousewheel True
                draggable True
                pagekeys True
                scrollbars "vertical"

                $ _pr_text = report.get("report_text", "报告内容为空") if report else "报告内容为空"
                text _pr_text:
                    size 24
                    color "#dddddd"
                    line_spacing 8

            textbutton "返回":
                xalign 0.5
                padding (40, 15)
                text_size 26
                text_color "#e67e22"
                action Hide("parent_report_detail")


# ============================================================
# Screen: 场景知识交互叠加层
# 在每个场景背景上显示可点击的知识热点图标
# ============================================================

screen scene_knowledge_overlay(scene_id="forest"):

    zorder 40

    $ _knowledge_items = SCENE_KNOWLEDGE_ITEMS.get(scene_id, [])

    for _ki in _knowledge_items:
        button:
            xpos _ki["xpos"]
            ypos _ki["ypos"]
            anchor (0.5, 0.5)
            xsize 96
            ysize 72
            background Solid("#FFD70055")
            hover_background Solid("#FFD700AA")
            at encyclopedia_pulse
            alt "探索知识点：[_ki['name']]"
            action Show("scene_knowledge_card", kn_name=_ki["name"], kn_desc=_ki["description"], kn_scene=scene_id)

            text "探索" size 20 color "#FFF8E1" xalign 0.5 yalign 0.5 bold True


# ============================================================
# Screen: 场景知识详情卡片
# ============================================================

screen scene_knowledge_card(kn_name="", kn_desc="", kn_scene=""):

    modal True
    zorder 170

    add Solid("#1a0f0588")

    frame:
        xalign 0.5 yalign 0.45
        xsize 700
        ysize 450
        padding (40, 35)
        background Solid("#3e2a15EE")

        vbox:
            spacing 20
            xfill True

            text "场景探索" size 22 color "#2ecc71" xalign 0.5

            text kn_name size 36 color "#FFD700" bold True xalign 0.5

            null height 5

            text kn_desc:
                size 24
                color "#dddddd"
                line_spacing 8
                text_align 0.5
                xalign 0.5

            null height 10

            hbox:
                xalign 0.5
                spacing 30

                if kn_name in get_forest_notes():
                    textbutton "已收藏 \u2713":
                        padding (25, 12)
                        text_size 22
                        text_color "#888888"
                        action NullAction()
                else:
                    textbutton "收藏到森林笔记":
                        padding (25, 12)
                        text_size 22
                        text_color "#2ecc71"
                        action [SetDict(get_forest_notes(), kn_name, {"description": kn_desc, "date": "", "scenario": kn_scene}), renpy.restart_interaction]

                textbutton "继续冒险":
                    padding (25, 12)
                    text_size 22
                    text_color "#f39c12"
                    action Hide("scene_knowledge_card")
