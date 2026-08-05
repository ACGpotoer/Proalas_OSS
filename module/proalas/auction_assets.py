# -*- coding: utf-8 -*-
"""
竞拍场（ProalasSpecialEvent / Auction）坐标与裁切模板。

素材：assets/cn/proalas_auction/（备份 0723-0807/）
裁切图须 load_image(file, area=None) 再 matchTemplate，勿 ensure_template。
"""
from module.base.button import Button

LIFECYCLE = '0723-0807'
EVENT_NAME = 'Auction'

# 主界面 → 竞拍
ENTER_CLICK_1 = (1000, 125)
ENTER_CLICK_2 = (1040, 650)
ENTER_GAP_SEC = 1.0

# 场次（竞拍列表页）
VENUE_B = (335, 450)
VENUE_A = (990, 420)
VENUE_S = (610, 300)
# 门票（进场消耗，仅日志参考）
TICKET_B = 100
TICKET_A = 5000
TICKET_S = 20000
# 选场门槛（持有虚拟币）：<1000k→B，<3000k→A，≥3000k→S
VENUE_COIN_A = 1_000_000   # 1000k
VENUE_COIN_S = 3_000_000   # 3000k
# 完成任务：≥8000k 出七位数(首位=QuestBidLevel)；场次另见 VenueSelect
QUEST_COIN_HIGH = 8_000_000  # 8000k
# 完成任务：目前中标 - 初始中标 ≥ 该值（也可被配置 TargetWins 覆盖）
QUEST_WIN_DELTA = 50
QUEST_ROUNDS_CAP = 80
# 兼容旧名
QUEST_WIN_CAP = QUEST_WIN_DELTA


START_AUCTION = (1100, 660)  # 开始竞拍 / 竞拍匹配

# 指标面板（浅底黑字）
STATS_OPEN = (1135, 60)
STATS_BACK = (490, 660)
OCR_AUCTION_COIN = (600, 390, 750, 430)
OCR_WIN_COUNT = (600, 340, 750, 380)
OCR_JOIN_COUNT = (380, 340, 490, 380)
OCR_LETTER_BLACK = (50, 50, 50)

# Buff
BUFF_PICK = (630, 580)
BUFF_CONFIRM = (1115, 430)  # 确认选择死坐标，防误点「本轮出价」

DIGIT_XY = {
    1: (115, 445), 2: (250, 445), 3: (385, 445),
    4: (115, 540), 5: (250, 540), 6: (385, 540),
    7: (115, 635), 8: (250, 635), 9: (385, 635),
}
BID_SUBMIT = (1000, 640)
BID_CONFIRM = (790, 490)
BID_CLEAR = (650, 540)   # 出价前必须先归零，否则会叠成八位数
# 结算：先点「一键跳过」模板中心，再点退出回列表
AREA_END = (480, 20, 670, 70)          # JPend 裁切区
JP_END_CLICK = (575, 45)               # AREA_END 中心 = 一键跳过
ROUND_EXIT = (1090, 640)               # 跳过后出现的退出按钮 → 回竞拍列表

LEAVE_BACK = (40, 45)
LEAVE_BACK_TIMES = 2
LEAVE_BACK_GAP = 1.0

# 模板匹配区（只在窗内搜，避免蓝按钮互误）
AREA_MAINVIEW = (1040, 610, 1230, 680)
AREA_CHOOSE_BUFF = (990, 400, 1240, 460)
AREA_BUY = (1040, 610, 1230, 680)
AREA_WAIT = (1040, 610, 1230, 680)
AREA_YES_PAY = (970, 610, 1220, 670)

JP_MAINVIEW = Button(
    area=AREA_MAINVIEW, color=(40, 90, 160), button=AREA_MAINVIEW,
    file='./assets/cn/proalas_auction/JPmainview.png', name='JP_MAINVIEW',
)
JP_WAIT = Button(
    area=AREA_WAIT, color=(40, 50, 70), button=AREA_WAIT,
    file='./assets/cn/proalas_auction/JPwait.png', name='JP_WAIT',
)
JP_CHOOSE_BUFF = Button(
    area=AREA_CHOOSE_BUFF, color=(30, 50, 90), button=AREA_CHOOSE_BUFF,
    file='./assets/cn/proalas_auction/JPchooseBuff.png', name='JP_CHOOSE_BUFF',
)
JP_BUY = Button(
    area=AREA_BUY, color=(40, 90, 160), button=AREA_BUY,
    file='./assets/cn/proalas_auction/JPbuy.png', name='JP_BUY',
)
JP_YES_PAY = Button(
    area=AREA_YES_PAY, color=(30, 50, 100), button=AREA_YES_PAY,
    file='./assets/cn/proalas_auction/JPyespay.png', name='JP_YES_PAY',
)
JP_END = Button(
    area=AREA_END, color=(50, 50, 55), button=AREA_END,
    file='./assets/cn/proalas_auction/JPend.png', name='JP_END',
)

MATCH_SIM = 0.80
MATCH_SIM_END = 0.75
POLL_SEC = 5.0
ROUNDS_CAP = 40
