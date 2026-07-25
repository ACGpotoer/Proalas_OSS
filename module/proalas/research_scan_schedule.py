# -*- coding: utf-8 -*-
"""定时计划：到期时触发科研船坞扫描。"""
from __future__ import annotations

from module.logger import logger
from module.proalas.collection_fill_policy import (
    collection_fill_enabled,
    research_fill_enabled,
    research_interval_days,
    research_scan_due,
)


def maybe_run_research_scan_if_due(config, device) -> bool:
    """
    定时计划 bundle 钩子。
    Returns:
        True 若本次执行了扫描。
    """
    config.load()
    config.bind('ProalasCollectionFill')
    data = config.data if hasattr(config, 'data') else {}

    if not collection_fill_enabled(data):
        logger.info('ResearchScan bundle skip: CollectionFill.Enable=false')
        return False
    if not research_fill_enabled(data):
        logger.info('ResearchScan bundle skip: ResearchEnable=false')
        return False
    if not research_scan_due(data):
        logger.info(
            'ResearchScan bundle skip: not due (interval=%sd)',
            research_interval_days(data),
        )
        return False

    from module.proalas.research_scan import ProalasResearchScan

    logger.info('ResearchScan bundle: weekly due — start')
    ProalasResearchScan(config=config, device=device).run(
        skip_gate=True,
        skip_task_delay=True,
    )
    return True
