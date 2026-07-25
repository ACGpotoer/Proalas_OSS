# -*- coding: utf-8 -*-
"""科研补齐 · 开发船坞扫描：模板与 OCR 区域。"""
from __future__ import annotations

from typing import Tuple

from module.base.button import Button

Area4 = Tuple[int, int, int, int]

# 船名 OCR（开发船坞详情页顶栏）
# 用户原给 (670,90)-(770,130) 过窄会切掉首字；过宽到 x570 易误读稀有度边
SHIP_NAME_AREA: Area4 = (580, 95, 750, 125)
SHIP_NAME_AREA_CANDIDATES: tuple[Area4, ...] = (
    (580, 95, 750, 125),
    (560, 90, 760, 128),
    (600, 92, 740, 122),
)

# 「开始研究」黄按钮（截图标定）
START_SCIENCE_BOAT_AREA: Area4 = (530, 490, 750, 550)
START_SCIENCE_BOAT = Button(
    area={'cn': START_SCIENCE_BOAT_AREA},
    color={'cn': (222, 194, 107)},
    button={'cn': START_SCIENCE_BOAT_AREA},
    file={'cn': './assets/cn/CollectionFill/StartScienceBoat.png'},
    name='StartScienceBoat',
)

# 「研究进行中...」——仅此模板判定「当前正在做的科研」
START_SCIENCE_BOAT_RUNNING_AREA: Area4 = (465, 480, 585, 500)
START_SCIENCE_BOAT_RUNNING = Button(
    area={'cn': START_SCIENCE_BOAT_RUNNING_AREA},
    color={'cn': (102, 114, 152)},
    button={'cn': START_SCIENCE_BOAT_RUNNING_AREA},
    file={'cn': './assets/cn/CollectionFill/StartScienceBoatRunning.png'},
    name='StartScienceBoatRunning',
)

# 「完成研究」橙钮（与开始研究同位置，互斥）
END_SCIENCE_BOAT_AREA: Area4 = (530, 490, 750, 550)
END_SCIENCE_BOAT = Button(
    area={'cn': END_SCIENCE_BOAT_AREA},
    color={'cn': (201, 121, 101)},
    button={'cn': END_SCIENCE_BOAT_AREA},
    file={'cn': './assets/cn/CollectionFill/EndScienceBoat.png'},
    name='EndScienceBoat',
)

# 点「完成研究」后不可交互结算页：同位置连点次数与间隔
END_SCIENCE_BOAT_CLICKS = 3
END_SCIENCE_BOAT_CLICK_INTERVAL = 1.0

# 全部科研补齐完成后，推迟下次扫描的天数
RESEARCH_ALL_DONE_PAUSE_DAYS = 180

# 科研详情右侧：阵营职责文案（xx主力 / xx先锋）
RESEARCH_FACTION_AREA: Area4 = (935, 130, 1145, 560)

# 科研任务列表 OCR（标题；与按钮匹配区分开）
RESEARCH_TASK_LIST_AREA: Area4 = (935, 130, 1145, 560)
# 提交 / LOCKED 控件搜索区（比列表更宽更靠下）
RESEARCH_TASK_BUTTON_AREA: Area4 = (1000, 430, 1280, 560)

# 列表滑动：上滑置顶 (1100,230)→(1100,520)；下滑相反；时长约 2s
RESEARCH_TASK_SWIPE_TOP: tuple[int, int] = (1100, 230)
RESEARCH_TASK_SWIPE_BOTTOM: tuple[int, int] = (1100, 520)
RESEARCH_TASK_SWIPE_DURATION = (2.0, 2.0)

# 任务关键字（罗马数字不强依赖 OCR）
RESEARCH_TASK_KEYWORDS: tuple[str, ...] = (
    '技术测试',
    '技术理论',
    '技术突破',
    '舰体塑造',
)

# 「提交」蓝钮（能交）；LOCKED 可选比对，实现上以能找到提交为准
SUBMIT_RESEARCH_TASK_AREA: Area4 = (1090, 500, 1230, 535)
# Button color 为 RGB；全屏模板均值（BGR→RGB）
SUBMIT_RESEARCH_TASK = Button(
    area={'cn': SUBMIT_RESEARCH_TASK_AREA},
    color={'cn': (83, 122, 191)},
    button={'cn': SUBMIT_RESEARCH_TASK_AREA},
    file={'cn': './assets/cn/CollectionFill/SubmitResearchTask.png'},
    name='SubmitResearchTask',
)

SUBMIT_NONE_AREA: Area4 = (1090, 445, 1230, 480)
SUBMIT_NONE = Button(
    area={'cn': SUBMIT_NONE_AREA},
    color={'cn': (99, 102, 112)},
    button={'cn': SUBMIT_NONE_AREA},
    file={'cn': './assets/cn/CollectionFill/SubmitNone.png'},
    name='SubmitNone',
)

# 提交钮用全屏模板；搜索区可略扩
SUBMIT_TEMPLATE_SIMILARITY = 0.75
SUBMIT_TEMPLATE_OFFSET = (40, 40)

# 略提高，减少 EMPTY/锁定页误触「开始研究」
TEMPLATE_SIMILARITY = 0.88
TEMPLATE_OFFSET = (20, 20)

# ---------- 科研进行中 · 底栏 8 阶段图标（仅 running 船出现）----------
# 中心：首 (490,525) → 末 (790,525)；步长 300/7；每格 30x30
RESEARCH_STAGE_COUNT = 8
RESEARCH_STAGE_FIRST_CENTER = (490, 525)
RESEARCH_STAGE_LAST_CENTER = (790, 525)
RESEARCH_STAGE_STEP_X = (RESEARCH_STAGE_LAST_CENTER[0] - RESEARCH_STAGE_FIRST_CENTER[0]) / (
    RESEARCH_STAGE_COUNT - 1
)
RESEARCH_STAGE_HALF = 15
RESEARCH_STAGE_DONE_FILE = './assets/cn/CollectionFill/ResearchStageDone.png'
RESEARCH_STAGE_LOCKED_FILE = './assets/cn/CollectionFill/ResearchStageLocked.png'
RESEARCH_STAGE_READY_FILE = './assets/cn/CollectionFill/ResearchStageReady.png'
# 互比对：自身~1.0，交叉 combined≲0.52 → 0.65 + 边距 0.10
RESEARCH_STAGE_SIMILARITY = 0.65
RESEARCH_STAGE_MARGIN = 0.10
# 左→右 = 上→下任务顺序（各期固定）
RESEARCH_STAGE_KEYWORDS: tuple[str, ...] = (
    '技术测试',  # 1
    '技术理论',  # 2
    '技术突破',  # 3
    '技术测试',  # 4
    '技术理论',  # 5
    '技术突破',  # 6
    '舰体塑造',  # 7
    '舰体塑造',  # 8
)
RESEARCH_STAGE_TECH_TEST_SLOTS: tuple[int, ...] = (1, 4)

# 切船后状态识别：额外等待 + 完成态复检，减少「开始研究」未刷新误判
RESEARCH_FOCUS_SETTLE_EXTRA = 0.45
RESEARCH_STATUS_RETRY_WAIT = 0.55

# 1–2 期最多 6 槽；3 期起每期固定 5 船，底部脸图位置沿用
SERIES_COUNT = 9


def max_ship_index(series: int) -> int:
    """3 期起固定 5 槽，不再按 nav 可见数量裁剪。"""
    return 6 if series <= 2 else 5


def series_label_cn(series: int) -> str:
    names = ('一', '二', '三', '四', '五', '六', '七', '八', '九')
    if 1 <= series <= len(names):
        return f'{names[series - 1]}期'
    return f'{series}期'


def incomplete_label(series: int, ship_name: str, index: int | None = None) -> str:
    name = (ship_name or '').strip()
    if not name:
        name = f'第{index}艘' if index else '未知舰'
    return f'{series_label_cn(series)}-{name}'
