# 熊出没奇遇 — 持久化数据初始化
# 使用 init -1 确保在其他 init python 块之前执行

init -1 python:
    # --------------------------------------------------------
    # 百科词条收集（森林笔记）
    # --------------------------------------------------------
    if persistent.forest_notes is None:
        persistent.forest_notes = {}
        # 格式: { "松鼠": {"description": "...", "date": "2026-03-16", "scenario": "..."}, ... }

    # --------------------------------------------------------
    # 结局图鉴
    # --------------------------------------------------------
    if persistent.endings_unlocked is None:
        persistent.endings_unlocked = []
        # 格式: [{"title": "...", "ending_type": "...", "character": "...",
        #         "scenario": "...", "score": 85, "date": "...", "summary": "..."}, ...]

    # --------------------------------------------------------
    # 勋章系统
    # --------------------------------------------------------
    if persistent.badges is None:
        persistent.badges = {}
        # 格式: { "badge_id": {"unlocked": True, "date": "2026-03-16"}, ... }

    # --------------------------------------------------------
    # 游玩统计
    # --------------------------------------------------------
    if persistent.play_stats is None:
        persistent.play_stats = {
            "total_plays": 0,
            "characters_used": [],
            "highest_score": 0,
            "character_play_counts": {},
        }

    # --------------------------------------------------------
    # 家长报告
    # --------------------------------------------------------
    if persistent.parent_reports is None:
        persistent.parent_reports = []
        # 格式: [{"date": "...", "character": "...", "scenario": "...",
        #         "stats_final": {}, "score": 85, "report_text": "..."}, ...]

    # --------------------------------------------------------
    # 多账户系统
    # --------------------------------------------------------
    if persistent.accounts is None:
        persistent.accounts = {}
    if persistent.account_order is None:
        persistent.account_order = []       # 正式账户 key 的有序列表
    if persistent.current_user is None:
        persistent.current_user = None      # 当前登录账户的 key
    if persistent.guest_counter is None:
        persistent.guest_counter = 0        # 游客累计编号（只增不减）
    if persistent.next_slot_index is None:
        persistent.next_slot_index = 0      # 存档位分配计数器（只增不减）
    if persistent.data_version is None:
        persistent.data_version = 0         # 数据版本号，用于迁移判断

    # --------------------------------------------------------
    # 拼音辅助识字模式
    # --------------------------------------------------------
    if persistent.pinyin_mode is None:
        persistent.pinyin_mode = False
