# -*- coding: utf-8 -*-
"""AI 规划三档策略：保守 / 激进 / 创新。"""
from __future__ import annotations

from typing import Any

STRATEGY_CONSERVATIVE = 'conservative'
STRATEGY_AGGRESSIVE = 'aggressive'
STRATEGY_INNOVATIVE = 'innovative'

DEFAULT_STRATEGY = STRATEGY_CONSERVATIVE

# WebUI ⚙ 说明（用户可见，与当前 executor 能力一致）
_STRATEGY_FOOTNOTE = (
    '\n\n【系统能力边界】'
    '规划仅调整 Scheduler 与白名单内任务参数、计划表备忘；'
    '不会自动更换活动 ID、配装、评估关卡能否打过，也无法保证满图鉴。'
)

STRATEGIES: dict[str, dict[str, str]] = {
    STRATEGY_CONSERVATIVE: {
        'label': '保守',
        'title': '保守策略',
        'help': (
            '维持资源平衡，调度偏稳。\n'
            '优先：委托、科研、收获、每日；主线（Campaign）按现有配置维持节奏，'
            '不额外压缩间隔或加强度。\n'
            '不主动加大 OPSI / Hard 强度；不为补图鉴消耗魔方（建船/大量退役等）。\n'
            '活动期：若活动任务已启用，倾向提高省油阈值（如 Event.StopCondition.OilLimit）、'
            '拉长间隔；不会自动修改 Campaign.Event。\n'
            '适合：长时间挂机、资源不多、希望少波动。'
            + _STRATEGY_FOOTNOTE
        ),
        'promptHint': (
            'strategyId=conservative。目标：稳资源、少消耗。\n'
            '优先 Commission/Research/Reward/Daily；Campaign 仅维持，不缩短 NextRun。\n'
            'Opsi/Hard/活动商店：task_delay 拉长（+60～+360min）或保持现状，勿主动提前。\n'
            '若 Event 已启用：可 set Event.StopCondition.OilLimit 偏高（如 15000～25000）。\n'
            'Commission：偏 cube/金，DoMajorCommission=false 倾向。\n'
            '禁止：为图鉴 set 魔方建船相关；禁止改 Campaign.Event。\n'
            '指令 3～6 条，宜少而稳。'
        ),
    },
    STRATEGY_AGGRESSIVE: {
        'label': '激进',
        'title': '激进策略',
        'help': (
            '在油/币允许时积极清任务、压缩间隔。\n'
            '优先缩短 Daily、Opsi、活动、Hard 等的 NextRun；委托偏向紧急/魔方类。\n'
            '可接受油币处于中低水平（为推进内容而消耗）。\n'
            '不推图时：倾向优先紧急委托。\n'
            '图鉴/收藏：可在规则内启用 ProalasAutoBreak 等已有任务，但不承诺满图鉴。\n'
            '不会：自动配装、自动判断某关能否打过、读取外部攻略库。\n'
            '适合：活动冲刺、资源较充足、希望尽快消化 pending 任务。'
            + _STRATEGY_FOOTNOTE
        ),
        'promptHint': (
            'strategyId=aggressive。前提：resources.stale=false 且 oil>=8000 或 money>=100000，'
            '否则降级为保守并 warnings 说明。\n'
            '优先 pendingCommands 与 Event/Opsi/Daily/Hard：task_delay minute=0～30 缩短。\n'
            'Commission：PresetFilter/CustomFilter 偏 urgent/cube；可缩短 NextRun。\n'
            'Event：可 set Event.StopCondition.OilLimit 偏低（如 5000～12000）以多出击。\n'
            'ProalasAutoEventShop/AutoBreak：若已启用可 task_delay 提前。\n'
            '禁止：改 Campaign.Event、配装、不可能的一次性满图鉴。\n'
            '指令 7～12 条。'
        ),
    },
    STRATEGY_INNOVATIVE: {
        'label': '创新·人工',
        'title': 'Pro+ 创新·人工',
        'help': (
            'Pro+ 套餐（在 Pro 基础上 +20 元/月），不是第三种机器人格。\n'
            '包含：Pro 全部自动化能力；可在「保守」「激进」两套宏之间切换；'
            '人工客服协助调参、排障与策略确认（次数与响应见购买须知）。\n'
            'Strategy 选「创新」仅表示 Pro+ 账户；实际跑 conservative 或 aggressive 宏，'
            '由您或客服指定。建议关闭 AutoApply，避免未经确认的批量改 config。\n'
            '未全自动的功能（配队、装备等）可由客服代改 config。\n'
            '适合：希望有人工兜底、需要灵活切换保守/激进的用户。'
            + _STRATEGY_FOOTNOTE
        ),
        'promptHint': (
            'strategyId=innovative 且 PlanType=pro_plus。\n'
            '本档不生成「AI 线性混合」排程；若用户未指定，默认等同 conservative 宏。\n'
            '若用户/客服明确要求激进：输出 aggressive preset 等价指令（仍遵守 stale/油币门槛）。\n'
            '人工备忘用 red_patch.note 或 warnings，禁止 plan_upsert。\n'
            '禁止：冒充全自动满图鉴/必过某关；改 Campaign.Event/Emulator/Scheduler.Enable。'
        ),
    },
}


def normalize_strategy(value: Any) -> str:
    key = str(value or '').strip().lower()
    if key in STRATEGIES:
        return key
    return DEFAULT_STRATEGY


def strategy_label(strategy_id: str) -> str:
    return STRATEGIES.get(normalize_strategy(strategy_id), {}).get('label', strategy_id)


def strategy_help(strategy_id: str) -> str:
    s = STRATEGIES.get(normalize_strategy(strategy_id), {})
    return f"{s.get('title', '')}\n\n{s.get('help', '')}"


def strategy_prompt_hint(strategy_id: str) -> str:
    return STRATEGIES.get(normalize_strategy(strategy_id), {}).get('promptHint', '')
