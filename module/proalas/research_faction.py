# -*- coding: utf-8 -*-
"""当前科研船阵营 OCR → 自动换队 LevelTeamFaction。"""
from __future__ import annotations

import re
from typing import Any

from module.CollectionFill.assets import RESEARCH_FACTION_AREA
from module.config.deep import deep_get, deep_set
from module.config.utils import filepath_config, read_file, write_file
from module.logger import logger
from module.ocr.ocr import Ocr

# 「xx主力 / xx先锋」
_ROLE_RE = re.compile(r'([\u4e00-\u9fffA-Za-z]{2,6})\s*(主力|先锋)')

# OCR 截取的 xx → 配置键（与 ProalasAutoFleetChange.LevelTeamFaction option 一致）
# 二字阵营直接对应；四字/特殊见映射
_FACTION_SHORT_TO_KEY: dict[str, str] = {
    '皇家': 'royal',
    '白鹰': 'eagle',
    '重樱': 'sakura',
    '铁血': 'iron',
    '东煌': 'dragon',
    # 四字系：先取短名再映射
    '撒丁': 'sardegna',
    '撒丁帝国': 'sardegna',
    '鸢尾': 'iris',
    '鸯尾': 'iris',  # OCR 常见误读
    '自由鸢尾': 'iris',
    '维希': 'vichya',
    '维希教廷': 'vichya',
    '郁金': 'tulipa',
    '郁金王国': 'tulipa',
    # 北方联合：UI/配队侧用 northern；展示简称北联
    '北方联合': 'northern',
    '北联': 'northern',
    '飓风': 'tempesta',
    '晶环': 'pedreria',
    '晶环联盟': 'pedreria',
    'META': 'meta',
    '其他': 'other',
}

_KEY_TO_LABEL_ZH: dict[str, str] = {
    'eagle': '白鹰',
    'royal': '皇家',
    'sakura': '重樱',
    'iron': '铁血',
    'dragon': '东煌',
    'sardegna': '撒丁帝国',
    'northern': '北联',
    'iris': '自由鸢尾',
    'vichya': '维希教廷',
    'tulipa': '郁金王国',
    'pedreria': '晶环联盟',
    'meta': 'META',
    'tempesta': '飓风',
    'other': '其他',
}


def normalize_faction_short(raw_xx: str) -> str:
    """从 OCR 的 xx 得到规范化短名（处理北方联合等）。"""
    s = str(raw_xx or '').strip()
    if not s:
        return ''
    # 优先完整命中
    if s in _FACTION_SHORT_TO_KEY:
        return s
    # 「北方联合」等长串里截短
    for key in ('北方联合', '撒丁帝国', '自由鸢尾', '维希教廷', '郁金王国', '晶环联盟'):
        if key in s:
            return key
    for key in ('撒丁', '鸢尾', '鸯尾', '郁金', '维希', '北联', '皇家', '白鹰', '重樱', '铁血', '东煌', '飓风', '晶环'):
        if key in s:
            return key
    return s


def faction_short_to_key(short: str) -> str | None:
    short = normalize_faction_short(short)
    if not short:
        return None
    return _FACTION_SHORT_TO_KEY.get(short)


def faction_key_label_zh(key: str) -> str:
    return _KEY_TO_LABEL_ZH.get(key, key)


def extract_role_faction(text: str) -> tuple[str, str] | None:
    """
    从 OCR 全文提取 (xx, 主力|先锋)。
    Returns:
        (short, role) 或 None
    """
    text = str(text or '').replace(' ', '').replace('\n', '')
    if not text:
        return None
    m = _ROLE_RE.search(text)
    if not m:
        return None
    short = normalize_faction_short(m.group(1))
    role = m.group(2)
    return short, role


def parse_faction_from_ocr_text(text: str) -> dict[str, Any] | None:
    """
    Returns:
        {short, role, key, labelZh} 或 None
    """
    extracted = extract_role_faction(text)
    if not extracted:
        return None
    short, role = extracted
    key = faction_short_to_key(short)
    if not key:
        logger.warning('ResearchFaction unknown short=%r from text=%r', short, text)
        return None
    return {
        'short': short,
        'role': role,
        'key': key,
        'labelZh': faction_key_label_zh(key),
        'rawText': text,
    }


def ocr_research_faction_panel(image) -> dict[str, Any] | None:
    """OCR 科研详情右侧阵营区，解析主力/先锋阵营。"""
    ocr = Ocr(
        [RESEARCH_FACTION_AREA],
        lang='cnocr',
        letter=(255, 255, 255),
        threshold=128,
        name='RESEARCH_FACTION_PANEL',
    )
    try:
        raw = ocr.ocr(image)
    except Exception as e:
        logger.warning('ResearchFaction OCR failed: %s', e)
        return None
    text = str(raw or '').strip()
    logger.info('ResearchFaction OCR raw=%r', text)
    return parse_faction_from_ocr_text(text)


def faction_from_task_title(text: str) -> dict[str, Any] | None:
    """
    从任务标题解析阵营（如「重樱先锋技术测试Ⅰ」）。
    角色：标题含「主力」→主力，含「先锋」→先锋，否则默认先锋。
    """
    raw = str(text or '').strip()
    if not raw:
        return None
    short = normalize_faction_short(raw)
    # normalize_faction_short 对无映射串可能原样返回整句；再扫关键字
    if short == raw or short not in _FACTION_SHORT_TO_KEY:
        short = ''
        for key in (
            '北方联合', '撒丁帝国', '自由鸢尾', '维希教廷', '郁金王国', '晶环联盟',
            '撒丁', '鸢尾', '鸯尾', '郁金', '维希', '北联', '皇家', '白鹰', '重樱',
            '铁血', '东煌', '飓风', '晶环',
        ):
            if key in raw:
                short = normalize_faction_short(key)
                break
    if not short:
        return None
    key = faction_short_to_key(short)
    if not key:
        return None
    role = '主力' if '主力' in raw else '先锋'
    return {
        'short': short,
        'role': role,
        'key': key,
        'labelZh': faction_key_label_zh(key),
        'rawText': raw,
    }


def apply_level_team_faction(config_name: str, faction_key: str) -> bool:
    """写入自动换队的练级队阵营（供 3/4 练级队使用）。"""
    if faction_key not in _KEY_TO_LABEL_ZH and faction_key != 'all':
        logger.warning('ResearchFaction reject invalid key=%s', faction_key)
        return False
    path = filepath_config(config_name)
    data = read_file(path)
    if not isinstance(data, dict):
        logger.warning('ResearchFaction config missing %s', path)
        return False
    deep_set(
        data,
        keys=['ProalasAutoFleetChange', 'ProalasAutoFleetChange', 'LevelTeamFaction'],
        value=faction_key,
    )
    write_file(path, data)
    logger.info(
        'ResearchFaction apply LevelTeamFaction=%s (%s) config=%s',
        faction_key,
        faction_key_label_zh(faction_key),
        path,
    )
    return True


def record_active_research_faction(config_data: dict, faction_info: dict[str, Any]) -> None:
    """把当前科研阵营摘要写入内存中的 research 块（随后随 scan 写盘）。"""
    research = deep_get(config_data, ['ProalasData', 'CollectionFill', 'research'], {})
    if not isinstance(research, dict):
        research = {}
    research['activeFactionKey'] = faction_info.get('key')
    research['activeFactionLabel'] = faction_info.get('labelZh')
    research['activeFactionRole'] = faction_info.get('role')
    research['activeFactionShort'] = faction_info.get('short')
