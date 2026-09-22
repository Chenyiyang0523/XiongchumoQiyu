# ============================================================
# 正式图片声明。资源路径由 tools/check_project.py 在发布前校验。
# ============================================================

# ------ 角色头像 ------
image side guangtouqiang = Transform("avatars/guangtouqiang.png", size=(120, 120))
image side xiongda = Transform("avatars/xiongda.png", size=(120, 120))
image side xionger = Transform("avatars/xionger.png", size=(120, 120))
image side jijiguowang = Transform("avatars/jijiguowang.png", size=(120, 120))
image side maomao = Transform("avatars/maomao.png", size=(120, 120))
image side zhaolin = Transform("avatars/zhaolin.png", size=(120, 120))
image side tiancaiwei = Transform("avatars/tiancaiwei.png", size=(120, 120))
image side damahou = Transform("avatars/damahou.png", size=(120, 120))
image side ergou = Transform("avatars/ergou.png", size=(120, 120))

# ------ 角色精灵 ------
image guangtouqiang normal = "sprites/guangtouqiang_normal.png"
image xiongda normal = "sprites/xiongda_normal.png"
image xionger normal = "sprites/xionger_normal.png"
image jijiguowang normal = "sprites/jijiguowang_normal.png"
image maomao normal = "sprites/maomao_normal.png"
image zhaolin normal = "sprites/zhaolin_normal.png"
image tiancaiwei normal = "sprites/tiancaiwei_normal.png"
image damahou normal = "sprites/damahou_normal.png"
image ergou normal = "sprites/ergou_normal.png"

# ------ 场景背景（显式声明，确保 scene/show 可靠加载） ------
image bg forest = Transform("bg/bg_forest.webp", xysize=(1920, 1080), fit="cover")
image bg cabin = Transform("bg/bg_cabin.webp", xysize=(1920, 1080), fit="cover")
image bg cave = Transform("bg/bg_cave.webp", xysize=(1920, 1080), fit="cover")
image bg riverside = Transform("bg/bg_riverside.webp", xysize=(1920, 1080), fit="cover")
image bg mountain = Transform("bg/bg_mountain.webp", xysize=(1920, 1080), fit="cover")
image bg village = Transform("bg/bg_village.webp", xysize=(1920, 1080), fit="cover")
