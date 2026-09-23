# 本地篇章：纯数据 + 确定性路由。读取存档或重复请求不会再发放奖励。
init -2 python:
    # 节点字段：场景、事件、观察方案、行动方案、合作方案。
    LOCAL_CAMPAIGNS = {
        "treasure": {
            "title": "森林古地图", "keywords": ("寻宝", "宝藏", "地图", "探险", "神秘"),
            "goal": "找到古地图上的森林宝藏", "reward": "一盒留给下一代的树种",
            "twist": "藏宝人并不是远方的旅行家，而是小时候的光头强；盒底还压着他的歪歪扭扭的签名。",
            "qte": "风把地图吹散了！接住飘落的纸片", "fact": "树种旅行|松鼠会把种子埋进土里。没有被吃掉的种子，有机会长成新树。",
            "beats": [
                ("forest", "松树下露出半张旧地图。蓝色水纹、棕色木屋和三个小人分别指向三条路。", "沿水纹寻找河岸刻痕", "到木屋寻找制图工具", "请伙伴们辨认三个小人"),
                ("forest", "两棵松树都系着红布，其中一条已经褪色。", "比较布条与地图的颜色", "从路边捡一根树枝作记号", "请伙伴回忆刚才的路标"),
                ("riverside", "一排石头露出水面，最远的一块却已经松动。", "在岸上看清石头是否牢固", "沿岸寻找平整的绕行小路", "请光头强带队从步桥通过"),
                ("cave", "树洞墙上画着三圈年轮，旁边留下一个方框。", "把圈数与地图上的数字对应", "在纸上拓下方框的轮廓", "让伙伴分头找同样的图案"),
                ("cabin", "旧工具箱里有一把钝头小铲，还有一张写着“别伤树根”的纸条。", "划出远离树根的查找范围", "把落叶轻轻扫到一边", "请光头强示范怎样保护树根"),
                ("forest", "地上有新鲜脚印，尽头却不是藏宝点，而是小松鼠的粮仓。", "分清松鼠脚印与地图标记", "把挪动的松果放回原位", "提醒伙伴绕开粮仓"),
                ("mountain", "从平坦观景台望下去，三条小路正好连成一片叶子。", "对照叶尖方向定位", "在地图上连好三个路标", "让伙伴互相核对位置"),
                ("forest", "叶尖所指的老树旁，木牌只写着“让森林越来越大”。", "猜一猜宝藏与树木的关系", "清理木牌旁的落叶", "邀请伙伴一起读出留言"),
                ("village", "木盒打开了，里面是树种和种植记录。你们要决定如何保管这份宝藏。", "按树种分类并写好记录", "准备花盆开始种植", "约好大家轮流照看幼苗"),
            ],
            "branches": [
                ("riverside", "你选了水纹路线。河岸石刻藏在倒影里，顺着水光才能看清方向。", "用地图对照倒影", "在岸边调整观察角度", "请伙伴读出完整的石刻"),
                ("cabin", "你选了工具路线。光头强找到了旧罗盘，但盒盖卡住了；蛮力只会弄坏它。", "看清盒盖上的小卡扣", "用布擦去卡扣里的泥", "请光头强帮忙打开罗盘"),
                ("cave", "你选了伙伴路线。三个小人是儿时探险队的记号，树洞里还留着队员的手印。", "比较手印与地图图标", "把三个手印描到纸上", "请大家讲述各自记得的线索"),
            ],
        },
        "sports": {
            "title": "森林运动会", "keywords": ("运动", "比赛", "吉吉", "接力"),
            "goal": "让每位伙伴都参加森林运动会", "reward": "一面写着全体队员名字的友谊旗",
            "twist": "吉吉打开冠军奖盒，里面竟然是一张志愿裁判证。原来照顾比赛公平的人也能站上领奖台。",
            "qte": "接力开始！跟着节奏传递接力棒", "fact": "运动热身|慢走和轻缓活动关节能帮助身体进入运动状态。感到不舒服时要停下休息。",
            "beats": [
                ("village", "吉吉敲响开赛小鼓，跑道图、器材箱和队员名单都还没有准备好。", "先检查跑道图", "先整理运动器材", "先听听队员的需求"),
                ("forest", "跑道的一段铺满松果，松鼠却正在收集它们。", "标出需要清理的范围", "把跑道上的松果装进篮子", "和松鼠商量临时存放点"),
                ("village", "接力队速度差别很大，熊二担心自己拖慢全队。", "比较每人的优势与路段", "陪熊二练习短距离传棒", "请队员轮流说出一个长处"),
                ("riverside", "饮水站摆好了，太阳却把长椅晒得热乎乎的。", "寻找有树荫的位置", "把轻便水杯搬到阴凉处", "请大家轮流值守补水站"),
                ("forest", "毛毛飞快跑完，却不小心漏过了一个路标。", "核对赛道示意图", "把路标放到更醒目的位置", "和裁判商量公平的重跑办法"),
                ("village", "跳远区的起跳线模糊了，两位伙伴都觉得自己站对了。", "重新测量起跳线", "用粉笔画一条清楚的新线", "请两位伙伴一起确认规则"),
                ("cabin", "奖牌丝带打了结，备用材料只够做一面大旗。", "画出节省材料的拼接图", "把丝带编成彩色旗边", "请每位队员在旗上签名"),
                ("forest", "最后一轮接力即将开始，观众的加油声比小鼓还响。", "再确认传棒区的位置", "做一次轻缓热身", "和队员约定接棒口令"),
                ("village", "接力棒安全抵达终点，每个人都付出了努力。颁奖词还缺最后一句。", "写下每个人的进步", "举起大家一起做的队旗", "邀请所有队员一起上台"),
            ],
            "branches": [
                ("forest", "你选了赛道路线。平坦长路与短坡路都能到终点，幼小队员更需要平稳的路面。", "比较两条路线的坡度", "在平路设置清楚的路标", "请不同队员试走后再决定"),
                ("cabin", "你选了器材路线。球筐少了一个轮子，备用拖绳却正好能用。", "检查哪些零件完好", "把球分装进轻便小篮", "请光头强维修球筐"),
                ("village", "你选了队员路线。蹦蹦想参加比赛，却不擅长跑步；记路线才是他的强项。", "为蹦蹦找一个适合的位置", "陪他练习举路标", "请队员共同分配任务"),
            ],
        },
        "rescue": {
            "title": "风雨后的家园", "keywords": ("风雨", "暴风", "重建", "木屋", "保卫", "家园"),
            "goal": "修复风雨后的木屋和森林小路", "reward": "一间向所有伙伴开放的避雨小屋",
            "twist": "最后一块木板背面写着“欢迎回来”。大家修好的不仅是木屋，还是一座早已被遗忘的森林驿站。",
            "qte": "阵风来了！一起扶稳地面的防雨布", "fact": "雨后出行|雨后应远离急流、松动的树枝和不稳的边坡，跟随可信任的成人选择安全路线。",
            "beats": [
                ("forest", "雨停了，光头强家的门牌歪在一边。屋外积水、工具和伙伴都需要安排。", "沿安全小路查看积水", "去木屋清点修补材料", "先确认伙伴们是否平安"),
                ("cabin", "屋顶滴水，地面有一小片湿滑区域。高处维修必须交给光头强。", "画出滴水位置交给光头强", "把地上的物品移到干处", "和伙伴围出安全通行区"),
                ("forest", "路边落下一根树枝，绕路的指示牌被泥点盖住了。", "辨认指示牌原来的箭头", "擦净低处的路牌", "提醒大家走已检查的小路"),
                ("cabin", "小木凳一高一低，装水的杯子差点滑下来。", "检查是哪条凳腿松动", "把杯子放到平稳桌面", "请光头强修好木凳"),
                ("riverside", "河水仍然很急，原来的近路暂时不能走。", "在地图上标出禁行区域", "在安全位置放置提醒牌", "约好大家结伴走远路"),
                ("forest", "一只小鸟落在矮灌木边，翅膀湿了，伙伴们都想靠近看看。", "从远处观察它的状态", "退后留出安静空间", "请光头强联系懂救护的人"),
                ("cabin", "修补材料不够铺满整面墙，但屋里还有可以重复利用的木板。", "量好需要修补的面积", "整理完好的旧木板", "请大家一起决定材料用途"),
                ("forest", "雨后的阳光照亮了小路，路边垃圾也露了出来。", "区分可回收和不可回收物", "用工具收拾安全的小杂物", "分组检查是否遗漏路段"),
                ("cabin", "门牌重新挂好了，小屋也恢复干燥。门口的告示要写上什么呢？", "记下雨后检查清单", "摆好备用雨伞和毛巾", "写上欢迎伙伴来避雨"),
            ],
            "branches": [
                ("riverside", "你选了巡查路线。近路被水淹住，远处木桥还有完整的护栏。大家决定先请成人检查。", "把两条路线标在地图上", "在岸上立好绕行标志", "请光头强检查步桥"),
                ("cabin", "你选了材料路线。纸箱外层湿了，但底下仍有几块干燥木板。", "区分受潮和完好的材料", "把干木板放到通风处", "请伙伴按用途分类"),
                ("cave", "你选了照应路线。熊二把伙伴们带到干燥树洞，可名单上还少了蹦蹦。", "核对最后看到蹦蹦的位置", "在安全地点大声呼唤", "请光头强带队寻找"),
            ],
        },
        "festival": {
            "title": "森林美食节", "keywords": ("美食", "蜂蜜", "食物", "旅游", "导游", "节日"),
            "goal": "办一场人人都能参与的森林美食节", "reward": "一本每位伙伴都留下配方的分享食谱",
            "twist": "最受欢迎的摊位竟然没有卖食物，而是在教大家写食谱。原来把方法分享出去，快乐还能继续长大。",
            "qte": "餐布要被风吹跑了！按住餐布的边角", "fact": "认识食材|不采食不认识的野果和蘑菇。处理食物前洗手，并请成人确认食材是否适合每位参与者。",
            "beats": [
                ("village", "美食节快开始了，菜单上只有蜂蜜。有人想看配方，有人想搭摊位，还有人惦记客人的口味。", "寻找旧食谱上的新点子", "准备干净的摊位用具", "询问伙伴想吃什么"),
                ("cabin", "蜂蜜罐的标签弄混了，光看颜色分不清装的是什么。", "阅读并核对原来的记录", "把未确认的罐子单独放好", "请光头强确认每个罐子的内容"),
                ("forest", "熊二看见鲜艳的野蘑菇，想把它们放进汤里。", "查阅可靠的食材图鉴", "把野蘑菇留在原地", "提醒大家只用确认过的食材"),
                ("cabin", "食谱写着三杯水配一杯米，现在只准备了半杯米。", "按比例算出需要的水量", "用量杯慢慢核对份量", "和伙伴一起复核配方"),
                ("village", "小客人说自己不能吃某种食材，菜单上却还没有清楚的标注。", "列出每道菜的配料", "制作容易看懂的食材卡", "请成人和客人一起确认选择"),
                ("riverside", "洗过的蔬果放在篮里，野餐点离河水太近了。", "比较附近平坦干燥的位置", "把轻便餐具搬到安全桌面", "请大家一起布置休息区"),
                ("village", "队伍变长了，熊二急着先拿自己的那一份。", "估算每轮能分出多少份", "先独自取走一份甜点", "邀请熊二一起帮忙分餐"),
                ("cabin", "剩下一点米和几种蔬菜，大家想避免浪费。", "核对还能安全使用的食材", "请成人帮助准备合适的份量", "征集伙伴的搭配建议"),
                ("village", "每个摊位都飘着香气，食谱本还有一页空白，等着大家留下今天的经验。", "写清用量和注意事项", "画出每道菜的制作顺序", "请每位伙伴签上分享留言"),
            ],
            "branches": [
                ("cave", "你选了食谱路线。旧食谱上“一勺”没有写大小，同样的配方可能做出不同味道。", "给量勺标好容量", "用清水先练习量取", "请大家约定同一种量勺"),
                ("cabin", "你选了摊位路线。长桌不够放下所有盘子，分成取餐和回收两个区域会更顺畅。", "画出摆放和通行的位置", "把餐具分区摆好", "请伙伴试走一遍取餐路线"),
                ("forest", "你选了口味路线。有人爱甜，有人想吃清淡的，还有人希望配料能单独选。", "记录每个人的需求", "准备独立的配料小碟", "一起设计可以自由搭配的菜单"),
            ],
        },
    }
    LOCAL_SCENES = {"forest": "狗熊岭森林", "cabin": "光头强家", "cave": "熊大熊二的树洞", "riverside": "狗熊岭河边", "mountain": "狗熊岭山顶", "village": "狗熊岭村庄"}

    def local_theme(scenario):
        for key in ("sports", "rescue", "festival", "treasure"):
            theme = LOCAL_CAMPAIGNS[key]
            if any(word in str(scenario or "") for word in theme["keywords"]):
                return theme
        return LOCAL_CAMPAIGNS["treasure"]

    def local_choice_code(answer):
        text = str(answer or "").strip()
        if text[:1].upper() in ("A", "B", "C") and (len(text) == 1 or text[1] in ".．、 :："):
            return text[:1].upper()
        if any(word in text.lower() for word in ("一起", "伙伴", "请", "帮助", "合作", "商量", "together", "help")):
            return "C"
        if any(word in text.lower() for word in ("搬", "跑", "动手", "搭", "整理", "修", "take", "build")):
            return "B"
        return "A"

    def local_wish_kind(text):
        if any(word in str(text) for word in ("发明", "修", "建", "工具", "造")):
            return ("巧手心愿：制作一件帮助伙伴的小工具", "cabin", "一辆牢固的小推车", "一只小车轮松了，心愿支线需要你和光头强把它修好。", "观察轮轴与车架的连接", "整理好合适的维修材料", "请光头强维修并一起检查")
        if any(word in str(text) for word in ("发现", "探索", "宝", "秘密", "找")):
            return ("探索心愿：找回一份被遗忘的森林记录", "cave", "一册旧日森林笔记", "树洞里有一本受潮的旧笔记，你的心愿支线是让里面的记录重新被读到。", "辨认尚且清楚的页码", "把笔记放到干燥通风处", "请伙伴分别抄录清楚的内容")
        return ("友谊心愿：帮助一位落后的伙伴重返队伍", "forest", "一条代表约定的友谊丝带", "蹦蹦因担心拖慢队伍而躲到一边。你的心愿支线是帮他找到适合自己的任务。", "了解蹦蹦擅长的事情", "陪蹦蹦练习一项小任务", "邀请队员说出需要他帮忙的地方")

    def local_node(game_ref, turn=None):
        theme = local_theme(getattr(game_ref, "scenario", ""))
        turn = int(getattr(game_ref, "turn_count", 0) if turn is None else turn)
        total = max(3, min(10, int(getattr(game_ref, "max_turns", 3))))
        answers = list(getattr(game_ref, "user_responses", []) or [])
        if turn == 1:
            route = "ABC".index(local_choice_code(answers[0] if answers else "A"))
            return theme["branches"][route]
        if turn == max(2, total // 2) and getattr(game_ref, "powerup", "") == "人物命运改写神器":
            wish = local_wish_kind(getattr(game_ref, "fate_text", ""))
            return (wish[1], wish[3], wish[4], wish[5], wish[6])
        if turn == total - 1 and getattr(game_ref, "_game_difficulty", "") == "青少年难度":
            return LOCAL_REASONING[theme["title"]][:5]
        # 3/5/7/10 轮均走到终章，长篇增加中段内容，不循环复用关卡。
        index = 0 if turn <= 0 else 1 + ((turn - 2) * 7 // max(1, total - 3))
        if total == 3 and turn >= 2:
            index = 8
        return theme["beats"][max(0, min(8, index))]

    def local_hint(game_ref):
        node = local_node(game_ref)
        theme = local_theme(getattr(game_ref, "scenario", ""))
        if node == LOCAL_REASONING[theme["title"]][:5]:
            return "蜂蜜提示：" + LOCAL_REASONING[theme["title"]][5]
        if getattr(game_ref, "_game_difficulty", "儿童难度") == "青少年难度":
            return "蜂蜜提示：先想想“" + node[2] + "”能获得什么证据，再比较动手和合作需要的资源。"
        return "蜂蜜提示：可以先试试“" + node[2] + "”。三种办法都能继续，选你想尝试的！"

    def local_ending(game_ref):
        theme = local_theme(getattr(game_ref, "scenario", ""))
        answers = list(getattr(game_ref, "user_responses", []) or [])
        route = local_choice_code(answers[0] if answers else "A")
        route_names = {"A": "细心观察", "B": "巧手行动", "C": "伙伴同行"}
        kind = getattr(game_ref, "ending_type", "") if getattr(game_ref, "powerup", "") == "结局指定神器" else ""
        kind = kind if kind in ("大团圆式结局", "意料之外结局", "留白式结局") else "大团圆式结局"
        line = "你们收获了" + theme["reward"] + "。夕阳下，伙伴们为彼此留出了圆桌旁的位置。"
        if kind == "意料之外结局":
            line = theme["twist"]
        elif kind == "留白式结局":
            line = "你们收获了" + theme["reward"] + "。归途中，一封盖着叶子印章的信滑到门边，信上只写着：明天，你们还愿意出发吗？"
        wish_turn = max(2, int(getattr(game_ref, "max_turns", 3)) // 2)
        if getattr(game_ref, "powerup", "") == "人物命运改写神器" and len(answers) > wish_turn:
            line += "心愿支线得到的" + local_wish_kind(getattr(game_ref, "fate_text", ""))[2] + "，也被珍惜地带回家。"
        return (theme["title"] + "：" + route_names[route], kind, line)

    def build_campaign_story(game_ref):
        if game_ref is None:
            return "【场景：狗熊岭森林】\n清晨的松林里，新的冒险正在等待你。"
        theme = local_theme(getattr(game_ref, "scenario", ""))
        turn = int(getattr(game_ref, "turn_count", 0))
        total = max(3, min(10, int(getattr(game_ref, "max_turns", 3))))
        answers = list(getattr(game_ref, "user_responses", []) or [])
        friend = _supporting_character(game_ref)
        lines = []
        if turn > 0 and answers:
            previous = local_node(game_ref, turn - 1)
            code = local_choice_code(answers[-1])
            choice = previous[2 + "ABC".index(code)]
            feedback = {"A": "线索变得清楚了，大家据此确定下一步。", "B": "一番动手后，眼前的准备有了实在的进展。", "C": "每位伙伴都分到了适合的任务，大家一起完成了这一步。"}[code]
            if previous == LOCAL_REASONING[theme["title"]][:5]:
                feedback = "伙伴们和你一起检验这个答案。"
            elif "独自" in choice:
                feedback = "你的甜点拿到了，可还在排队的伙伴有些失落。下次可以先商量怎样公平分配。"
            lines.append("你决定“" + choice + "”。" + feedback)
            if not (str(answers[-1])[:2] in ("A.", "B.", "C.") or str(answers[-1]) in ("A", "B", "C")):
                lines.append("你的新想法被记进了冒险本，本次按" + {"A": "观察", "B": "行动", "C": "合作"}[code] + "路线尝试。")
            changes, _ = _local_choice_effect(answers[-1])
            if previous == LOCAL_REASONING[theme["title"]][:5]:
                correct = LOCAL_REASONING_ANSWERS[theme["title"]]
                if code == correct:
                    lines.append("推理验证正确！你把依据讲清楚，大家放心地采用了这个办法。")
                    changes = {"智": 2, "勇": 1}
                else:
                    lines.append("一起复核后发现答案是“" + previous[2 + "ABC".index(correct)] + "”。" + LOCAL_REASONING[theme["title"]][5] + " 试错也是探索的一部分。")
                    changes = {"智": 1}
            lines.append("【属性变化：" + "，".join(k + ("+" if v >= 0 else "") + str(v) for k, v in changes.items()) + "】")
            if getattr(game_ref, "last_qte_success", None) is not None and turn == max(1, total // 2) + 1:
                lines.append("刚才的行动挑战顺利完成，伙伴们精神十足。" if game_ref.last_qte_success else "刚才慢了一点，伙伴们帮忙收好东西。休息后继续出发，不会错过结局。")
        if turn >= total:
            title, kind, ending = local_ending(game_ref)
            lines.insert(0, "【场景：狗熊岭村庄】")
            lines += ["**" + friend + "**[开心]：“咱们做到了！”" , ending, "【剧终】"]
            return "\n".join(lines)
        node = local_node(game_ref, turn)
        lines.insert(0, "【场景：" + LOCAL_SCENES[node[0]] + "】")
        if turn == 0:
            lines.append("本次篇章：" + theme["title"] + "。目标是" + theme["goal"] + "。")
        lines.append(node[1])
        if getattr(game_ref, "_game_difficulty", "儿童难度") == "青少年难度":
            lines.append("**" + friend + "**[思考]：“先说明判断的依据，再考虑时间、材料和伙伴需要；同一难题也可以有不同办法。”")
        else:
            lines.append("**" + friend + "**[开心]：“先看看眼前的线索，再选一个办法试试吧！”")
        if turn == max(1, total // 2):
            lines.append("【百科：" + theme["fact"] + "】")
            lines.append("【QTE：" + theme["qte"] + "|点击|" + ("5" if getattr(game_ref, "_game_difficulty", "") == "青少年难度" else "7") + "】")
        lines.append("**请选择：**")
        for i, letter in enumerate("ABC"):
            option = node[2 + i]
            if getattr(game_ref, "_game_difficulty", "") == "青少年难度" and node != LOCAL_REASONING[theme["title"]][:5]:
                option += ("，先验证再判断", "，先检查材料和安全", "，先商量分工与理由")[i]
            lines.append(letter + ". " + option)
        return "\n".join(lines)

init -1 python:
    LOCAL_REASONING = {
        "森林古地图": ("cave", "进阶谜题：地图要求先向东走两格，再向西走一格。终点在起点的哪一边？", "东边一格", "西边一格", "仍在起点", "先画两步向东的箭头，再划掉一步向西的路程。"),
        "森林运动会": ("village", "进阶谜题：四位队员各跑一段，两段各长一百米，另两段各长五十米。全程是多少米？", "两百米", "三百米", "四百米", "分别算出两条长路和两条短路，再把结果相加。"),
        "风雨后的家园": ("cabin", "进阶谜题：九块新木板和三块可用旧木板，每处修补需要两块。最多能修补几处？", "三处", "五处", "六处", "旧木板也可以使用；先合计，再按每处两块分组。"),
        "森林美食节": ("cabin", "进阶谜题：三杯水配一杯米。现在用半杯米，保持同样比例需要多少水？", "一杯半", "三杯", "半杯", "米的份量减半，水的份量也要减半。"),
    }
    LOCAL_REASONING_ANSWERS = {"森林古地图": "A", "森林运动会": "B", "风雨后的家园": "C", "森林美食节": "A"}

screen family_discussion():
    modal True
    zorder 180
    add Solid("#102B24E8")
    frame:
        xalign 0.5 yalign 0.5
        xsize 1100
        padding (55, 40)
        background Solid("#24483C")
        vbox:
            spacing 24
            text "亲子讨论时间" size 38 color "#FFD166" xalign 0.5
            text "先请小朋友说说：刚才为什么选择这条路线？" size 28 color "#FFFFFF"
            text "再请大朋友提出另一种办法。一起猜猜，两种办法会带来什么不同？" size 26 color "#D8E9D8" xmaximum 990
            textbutton "我们聊了选择的理由":
                text_size 28
                text_color "#FFD166"
                action Return("讨论了选择的理由")
            textbutton "我们比较了另一种办法":
                text_size 28
                text_color "#FFD166"
                action Return("比较了不同的办法")
            textbutton "先继续冒险，稍后再聊":
                text_size 24
                text_color "#D8E9D8"
                action Return("稍后讨论")
