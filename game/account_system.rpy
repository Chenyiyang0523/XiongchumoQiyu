# 熊出没奇遇 — 多账户管理系统
# 包含：数据访问层、账户管理函数、迁移逻辑、账户选择 UI、splashscreen 入口

# ============================================================
# 数据访问层 + 账户管理函数
# ============================================================

init python:
    import copy
    import time as _account_time

    # --------------------------------------------------------
    # 默认账户数据模板
    # --------------------------------------------------------
    def _make_empty_account_data(name, is_guest=False, slot_index=0):
        return {
            "schema_version": 2,
            "name": name,
            "created_date": _account_time.strftime("%Y-%m-%d"),
            "is_guest": is_guest,
            "slot_index": slot_index,
            "forest_notes": {},
            "endings_unlocked": [],
            "badges": {},
            "play_stats": {
                "total_plays": 0,
                "characters_used": [],
                "highest_score": 0,
                "character_play_counts": {},
            },
            "parent_reports": [],
            "committed_runs": [],
        }

    def _safe_list(value):
        return value if isinstance(value, list) else []

    def _safe_dict(value):
        return value if isinstance(value, dict) else {}

    def _safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    def repair_account_data(account_key, account):
        """幂等修复旧版或部分损坏的账户结构。"""
        if not isinstance(account, dict):
            account = _make_empty_account_data("恢复账户", slot_index=0)
            persistent.accounts[account_key] = account
        account["schema_version"] = 2
        account["name"] = str(account.get("name") or "未命名账户")[:6]
        account["created_date"] = str(account.get("created_date") or _account_time.strftime("%Y-%m-%d"))
        account["is_guest"] = bool(account.get("is_guest", False))
        try:
            account["slot_index"] = max(0, int(account.get("slot_index", 0)))
        except (TypeError, ValueError):
            account["slot_index"] = 0
        account["forest_notes"] = _safe_dict(account.get("forest_notes"))
        account["endings_unlocked"] = _safe_list(account.get("endings_unlocked"))
        account["badges"] = _safe_dict(account.get("badges"))
        account["parent_reports"] = _safe_list(account.get("parent_reports"))
        account["committed_runs"] = _safe_list(account.get("committed_runs"))[-200:]
        stats = _safe_dict(account.get("play_stats"))
        account["play_stats"] = {
            "total_plays": max(0, _safe_int(stats.get("total_plays", 0))),
            "characters_used": _safe_list(stats.get("characters_used")),
            "highest_score": max(0, min(100, _safe_int(stats.get("highest_score", 0)))),
            "character_play_counts": _safe_dict(stats.get("character_play_counts")),
        }
        return account

    def repair_all_accounts():
        if not isinstance(persistent.accounts, dict):
            persistent.accounts = {}
        if not isinstance(persistent.account_order, list):
            persistent.account_order = []
        seen_slots = set()
        for key in list(persistent.accounts.keys()):
            account = repair_account_data(key, persistent.accounts[key])
            slot_index = account["slot_index"]
            if slot_index in seen_slots:
                slot_index = 0
                while slot_index in seen_slots:
                    slot_index += 1
                account["slot_index"] = slot_index
            seen_slots.add(slot_index)
        persistent.account_order = [
            key for key in persistent.account_order
            if key in persistent.accounts and not persistent.accounts[key].get("is_guest", False)
        ]
        for key, account in persistent.accounts.items():
            if not account.get("is_guest", False) and key not in persistent.account_order:
                persistent.account_order.append(key)
        if persistent.current_user not in persistent.accounts:
            persistent.current_user = None
        persistent.next_slot_index = (max(seen_slots) + 1) if seen_slots else 0

    # --------------------------------------------------------
    # 数据访问层 — 所有业务代码通过这些函数访问当前账户数据
    # 返回的是引用，修改会直接反映到 persistent 中
    # --------------------------------------------------------
    def get_current_account():
        if persistent.current_user and persistent.current_user in persistent.accounts:
            return repair_account_data(
                persistent.current_user,
                persistent.accounts[persistent.current_user]
            )
        return None

    def get_forest_notes():
        acc = get_current_account()
        if acc:
            return acc["forest_notes"]
        return {}

    def get_endings_unlocked():
        acc = get_current_account()
        if acc:
            return acc["endings_unlocked"]
        return []

    def get_badges():
        acc = get_current_account()
        if acc:
            return acc["badges"]
        return {}

    def get_play_stats():
        acc = get_current_account()
        if acc:
            return acc["play_stats"]
        return {"total_plays": 0, "characters_used": [], "highest_score": 0, "character_play_counts": {}}

    def get_parent_reports():
        acc = get_current_account()
        if acc:
            return acc["parent_reports"]
        return []

    # --------------------------------------------------------
    # 存档页码计算
    # --------------------------------------------------------
    def get_user_page_range(account_key):
        """返回 (start_page, end_page)，每个账户分配 4 页存档"""
        if not account_key or account_key not in persistent.accounts:
            return (1, 4)
        slot_index = persistent.accounts[account_key].get("slot_index", 0)
        start = slot_index * 4 + 1
        end = slot_index * 4 + 4
        return (start, end)

    def get_account_quick_page(account_key=None):
        """使用账户第 4 页中 UI 不展示的 12 号位作为私有快存。"""
        _start, end = get_user_page_range(account_key or persistent.current_user)
        return str(end)

    def get_account_quick_slot():
        return 12

    def _allocate_slot_index():
        used = set()
        for account in persistent.accounts.values():
            if isinstance(account, dict):
                try:
                    used.add(int(account.get("slot_index", 0)))
                except (TypeError, ValueError):
                    pass
        candidate = 0
        while candidate in used:
            candidate += 1
        persistent.next_slot_index = max(_safe_int(persistent.next_slot_index, 0), candidate + 1)
        return candidate

    # --------------------------------------------------------
    # 账户管理
    # --------------------------------------------------------
    def create_account(name):
        """创建正式账户，返回 account_key 或 None（已满）"""
        if len(persistent.account_order) >= 25:
            return None
        name = name.strip()
        if not name or len(name) > 6:
            return None
        slot_index = _allocate_slot_index()
        key = "user_" + str(slot_index)
        persistent.accounts[key] = _make_empty_account_data(name, is_guest=False, slot_index=slot_index)
        persistent.account_order.append(key)
        renpy.save_persistent()
        return key

    def create_guest():
        """创建游客账户，返回 account_key 或 None（已满）"""
        guest_count = sum(1 for k, v in persistent.accounts.items() if v.get("is_guest", False))
        if guest_count >= 25:
            return None
        persistent.guest_counter += 1
        slot_index = _allocate_slot_index()
        key = "_guest_" + str(persistent.guest_counter)
        persistent.accounts[key] = _make_empty_account_data("游客", is_guest=True, slot_index=slot_index)
        renpy.save_persistent()
        return key

    def switch_account(account_key):
        """切换到指定账户，如果旧账户是游客则自动清理"""
        if not account_key or account_key not in persistent.accounts:
            return False
        old_key = persistent.current_user
        if old_key and old_key != account_key and old_key in persistent.accounts:
            if persistent.accounts[old_key].get("is_guest", False):
                cleanup_guest(old_key)
        persistent.current_user = account_key
        start_page, _end_page = get_user_page_range(account_key)
        persistent._file_page = str(start_page)
        renpy.save_persistent()
        return True

    def delete_account(account_key):
        """删除指定账户及其存档"""
        if account_key not in persistent.accounts:
            return False
        delete_saves_for_account(account_key)
        del persistent.accounts[account_key]
        if account_key in persistent.account_order:
            persistent.account_order.remove(account_key)
        if persistent.current_user == account_key:
            persistent.current_user = None
        renpy.save_persistent()
        return True

    def cleanup_guest(account_key):
        """清理游客账户数据和存档"""
        if account_key not in persistent.accounts:
            return
        delete_saves_for_account(account_key)
        del persistent.accounts[account_key]
        if persistent.current_user == account_key:
            persistent.current_user = None
        renpy.save_persistent()

    def cleanup_all_guests():
        """启动时清扫所有残留的游客数据"""
        guest_keys = [k for k, v in persistent.accounts.items() if v.get("is_guest", False)]
        for gk in guest_keys:
            cleanup_guest(gk)

    def delete_saves_for_account(account_key):
        """删除指定账户存档页范围内的所有存档文件"""
        start_page, end_page = get_user_page_range(account_key)
        slots_per_page = 12
        for page in range(start_page, end_page + 1):
            for slot in range(1, slots_per_page + 1):
                slot_name = str(page) + "-" + str(slot)
                try:
                    renpy.unlink_save(slot_name)
                except Exception:
                    pass

    def get_current_user_name():
        """获取当前账户显示名称"""
        acc = get_current_account()
        if acc:
            return acc["name"]
        return ""

    def is_current_user_guest():
        """当前账户是否为游客"""
        acc = get_current_account()
        if acc:
            return acc.get("is_guest", False)
        return False

    # --------------------------------------------------------
    # 旧数据迁移
    # --------------------------------------------------------
    def migrate_legacy_data():
        """将旧版单用户 persistent 数据迁移到多账户结构"""
        if persistent.data_version and persistent.data_version >= 1:
            # 极少数旧测试包会只写入版本号，却没有成功落下 accounts。
            # 此时保留顶层数据并重新执行迁移，避免一次启动就清空玩家记录。
            if not isinstance(persistent.accounts, dict) or not persistent.accounts:
                persistent.data_version = 0
            else:
                repair_all_accounts()
                # v1 已复制过数据，v2 清理顶层重复，避免删除账户后仍残留个人记录。
                persistent.forest_notes = {}
                persistent.endings_unlocked = []
                persistent.badges = {}
                persistent.play_stats = {
                    "total_plays": 0, "characters_used": [],
                    "highest_score": 0, "character_play_counts": {},
                }
                persistent.parent_reports = []
                persistent.data_version = 2
                renpy.save_persistent()
                return

        has_old_data = (
            bool(persistent.forest_notes) or
            bool(persistent.endings_unlocked) or
            bool(persistent.badges) or
            _safe_dict(persistent.play_stats).get("total_plays", 0) > 0 or
            bool(persistent.parent_reports)
        )

        if has_old_data:
            slot_index = _allocate_slot_index()
            key = "user_" + str(slot_index)

            account_data = _make_empty_account_data("默认账户", is_guest=False, slot_index=slot_index)
            account_data["forest_notes"] = copy.deepcopy(persistent.forest_notes) if persistent.forest_notes else {}
            account_data["endings_unlocked"] = copy.deepcopy(persistent.endings_unlocked) if persistent.endings_unlocked else []
            account_data["badges"] = copy.deepcopy(persistent.badges) if persistent.badges else {}
            account_data["play_stats"] = copy.deepcopy(persistent.play_stats) if persistent.play_stats else account_data["play_stats"]
            account_data["parent_reports"] = copy.deepcopy(persistent.parent_reports) if persistent.parent_reports else []

            persistent.accounts[key] = account_data
            persistent.account_order.append(key)
            persistent.current_user = key

        persistent.forest_notes = {}
        persistent.endings_unlocked = []
        persistent.badges = {}
        persistent.play_stats = {
            "total_plays": 0, "characters_used": [],
            "highest_score": 0, "character_play_counts": {},
        }
        persistent.parent_reports = []
        persistent.data_version = 2
        repair_all_accounts()
        renpy.save_persistent()


# ============================================================
# ATL Transform 动画（账户选择界面专用）
# ============================================================

transform account_card_hover:
    on idle:
        ease 0.15 zoom 1.0
    on hover:
        ease 0.15 zoom 1.05

transform account_fade_in:
    alpha 0.0 yoffset 30
    ease 0.4 alpha 1.0 yoffset 0


# ============================================================
# Screen: 账户选择界面
# 返回值：account_key 字符串 | "__create__" | "__guest__"
# ============================================================

screen account_select():

    tag menu
    modal True
    zorder 200

    add Transform("bg/bg_forest.webp", xysize=(1920, 1080), fit="cover")
    add Solid("#14251CDD")

    frame:
        xfill True yfill True
        background None

        vbox:
            xalign 0.5 yalign 0.5
            spacing 30
            at account_fade_in

            # 标题
            text "选择账户":
                xalign 0.5
                size 48
                font "ZCOOLKuaiLe-Regular.ttf"
                color "#F6B73C"
                bold True
                outlines [(3, "#00000088", 0, 0)]

            text "熊出没奇遇":
                xalign 0.5
                size 24
                color "#FFF4D6"

            null height 10

            # 已有账户列表
            if persistent.account_order:
                viewport:
                    xalign 0.5
                    xmaximum 900
                    ymaximum 400
                    scrollbars "vertical"
                    mousewheel True
                    draggable True
                    pagekeys True
                    vscrollbar_xsize 18
                    vscrollbar_base_bar Solid("#31483A")
                    vscrollbar_thumb Solid("#F6B73C")
                    vscrollbar_hover_thumb Solid("#FFD166")
                    vscrollbar_unscrollable "hide"

                    vbox:
                        spacing 12
                        xalign 0.5

                        for _acc_key in persistent.account_order:
                            if _acc_key in persistent.accounts:
                                $ _acc = persistent.accounts[_acc_key]
                                $ _acc_name = _acc.get("name", "???")
                                $ _acc_plays = _acc.get("play_stats", {}).get("total_plays", 0)
                                $ _acc_badges = len(_acc.get("badges", {}))
                                $ _acc_endings = len(_acc.get("endings_unlocked", []))

                                hbox:
                                    xfill True
                                    xmaximum 800
                                    xalign 0.5
                                    spacing 12

                                    button:
                                        xsize 680
                                        padding (24, 16)
                                        background Solid("#203B2BEF")
                                        hover_background Solid("#315B3FFF")
                                        action Return(_acc_key)
                                        at account_card_hover

                                        vbox:
                                            spacing 4
                                            hbox:
                                                spacing 12
                                                text _acc_name size 28 color "#FFF4D6" bold True
                                                if persistent.current_user == _acc_key:
                                                    frame:
                                                        background Solid("#F6B73C")
                                                        padding (10, 3)
                                                        yalign 0.5
                                                        text "当前" size 16 color "#14251C"
                                            hbox:
                                                spacing 15
                                                text "冒险 [_acc_plays] 次" size 16 color "#BFD8C4"
                                                text "勋章 [_acc_badges] 枚" size 16 color "#F6B73C"
                                                text "结局 [_acc_endings] 个" size 16 color "#9ED0B0"

                                    textbutton "删除":
                                        xsize 100
                                        ysize 86
                                        yalign 0.5
                                        padding (18, 14)
                                        background Solid("#5A351FEE")
                                        hover_background Solid("#8A3B32")
                                        text_size 18
                                        text_color "#FFF4D6"
                                        text_xalign 0.5
                                        action Show("confirm_delete_account", account_key=_acc_key)

            else:
                text "还没有账户，点击下方按钮创建":
                    xalign 0.5
                    size 20
                    color "#BFD8C4"

            null height 10

            # 底部操作按钮
            hbox:
                xalign 0.5
                spacing 30

                # 新建账户
                if len(persistent.account_order) < 25:
                    textbutton "新建账户":
                        xsize 240
                        padding (28, 16)
                        background Solid("#F6B73C")
                        hover_background Solid("#FFD166")
                        text_size 26
                        text_color "#14251C"
                        text_xalign 0.5
                        text_bold True
                        action Return("__create__")
                else:
                    text "账户已满（25/25）" size 20 color "#ff6666" yalign 0.5

                # 游客模式
                textbutton "游客模式":
                    xsize 240
                    padding (28, 16)
                    background Solid("#2F6B3F")
                    hover_background Solid("#3D8551")
                    text_size 26
                    text_color "#FFF4D6"
                    text_xalign 0.5
                    text_bold True
                    action Return("__guest__")


# ============================================================
# Screen: 删除账户确认弹窗
# ============================================================

screen confirm_delete_account(account_key):

    modal True
    zorder 200

    add Solid("#000000BB")

    frame:
        xalign 0.5 yalign 0.5
        xsize 500
        padding (40, 30, 40, 30)
        background Solid("#14251CF5")

        vbox:
            spacing 20
            xalign 0.5

            text "确认删除账户" xalign 0.5 size 28 color "#FFB4A9" bold True

            if account_key in persistent.accounts:
                $ _del_acc = persistent.accounts[account_key]
                $ _del_name = _del_acc.get("name", "???")
                $ _del_plays = _del_acc.get("play_stats", {}).get("total_plays", 0)
                $ _del_badges = len(_del_acc.get("badges", {}))

                text "即将删除账户「[_del_name]」" xalign 0.5 size 20 color "#FFF4D6"

                hbox:
                    xalign 0.5
                    spacing 20
                    text "冒险 [_del_plays] 次" size 16 color "#BFD8C4"
                    text "勋章 [_del_badges] 枚" size 16 color "#F6B73C"

                text "删除后所有数据和存档将永久丢失！" xalign 0.5 size 18 color "#ff4444" bold True

            null height 10

            hbox:
                xalign 0.5
                spacing 30

                textbutton "确认删除":
                    text_size 22
                    text_color "#ff4444"
                    text_hover_color "#ff6666"
                    text_bold True
                    action [Function(delete_account, account_key), Hide("confirm_delete_account")]

                textbutton "取消":
                    text_size 22
                    text_color "#aaaaaa"
                    text_hover_color "#ffffff"
                    action Hide("confirm_delete_account")


# ============================================================
# Screen: 迁移通知
# ============================================================

screen migration_notice():

    modal True
    zorder 200

    add Solid("#000000BB")

    frame:
        xalign 0.5 yalign 0.5
        xsize 500
        padding (40, 30, 40, 30)
        background Solid("#2d2d44")

        vbox:
            spacing 20
            xalign 0.5

            text "数据迁移完成" xalign 0.5 size 28 color "#FFD700" bold True
            text "您的游戏数据已迁移到「默认账户」中。" xalign 0.5 size 18 color "#cccccc" text_align 0.5
            text "您可以在账户选择界面管理多个账户。" xalign 0.5 size 16 color "#aaaaaa" text_align 0.5

            null height 10

            textbutton "知道了":
                xalign 0.5
                text_size 22
                text_color "#4CAF50"
                text_hover_color "#66BB6A"
                text_bold True
                action Return()


# ============================================================
# Splashscreen — 游戏启动时的账户选择入口
# ============================================================

label splashscreen:

    # 执行数据迁移
    python:
        _did_migrate = (persistent.data_version == 0 and (
            bool(persistent.forest_notes) or
            bool(persistent.endings_unlocked) or
            bool(persistent.badges) or
            _safe_dict(persistent.play_stats).get("total_plays", 0) > 0 or
            bool(persistent.parent_reports)
        ))
        migrate_legacy_data()
        repair_all_accounts()
        cleanup_all_guests()

    # 如果发生了迁移，显示通知
    if _did_migrate:
        call screen migration_notice

    call account_hub

    return

label account_hub:

    $ repair_all_accounts()

label .select_loop:

    # 显示账户选择界面
    call screen account_select

    if _return == "__create__":
        # 新建账户流程：使用 renpy.input 获取名称
        $ _new_name = renpy.input("请输入账户名称（1-6个字符）：", length=6, default="")
        $ _new_name = _new_name.strip() if _new_name else ""
        if _new_name:
            $ _new_key = create_account(_new_name)
            if _new_key:
                $ switch_account(_new_key)
                jump .select_done
            else:
                "账户已满或名称无效，请重试。"
        else:
            "名称不能为空，请重试。"
        jump .select_loop

    elif _return == "__guest__":
        # 游客模式
        $ _guest_key = create_guest()
        if _guest_key:
            $ switch_account(_guest_key)
            jump .select_done
        else:
            "游客数量已满，请重试。"
            jump .select_loop

    else:
        # 选择了已有账户
        if _return and _return in persistent.accounts:
            $ switch_account(_return)
            jump .select_done
        jump .select_loop

label .select_done:

    return
