# -*- coding: utf-8 -*-
"""ProAlas 日志：对 module/proalas 输出隐藏坐标数值。"""
from __future__ import annotations

import logging
import re

_AREA4_RE = re.compile(
    r'\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)',
)
_PAIR_RE = re.compile(
    r'\(\s*\d+\s*,\s*\d+\s*\)',
)

_PROALAS_PATH_MARK = '/proalas/'


def scrub_coords(text: str) -> str:
    if not text:
        return text
    out = _AREA4_RE.sub('(*,*,*,*)', text)
    out = _PAIR_RE.sub('(*,*)', out)
    return out


def _is_proalas_record(record: logging.LogRecord) -> bool:
    path = str(getattr(record, 'pathname', '') or '').replace('\\', '/').lower()
    if _PROALAS_PATH_MARK in path:
        return True
    name = str(getattr(record, 'name', '') or '')
    return name.startswith('module.proalas')


class ProalasCoordScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not _is_proalas_record(record):
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        scrubbed = scrub_coords(message)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()
        return True


_installed = False


def install_proalas_coord_scrub() -> None:
    """向 Alas 主 logger 注册坐标脱敏（幂等）。"""
    global _installed
    if _installed:
        return
    from module.logger import logger

    logger.addFilter(ProalasCoordScrubFilter())
    _installed = True
