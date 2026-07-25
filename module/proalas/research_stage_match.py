# -*- coding: utf-8 -*-
"""科研进行中：底栏 8 格阶段图标 RD / RI / RY 匹配。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np

from module.CollectionFill import assets as A
from module.logger import logger

# status: 'done' | 'locked' | 'ready' | 'unknown'


@lru_cache(maxsize=1)
def _load_templates() -> dict[str, np.ndarray]:
    """BGR 30x30。"""
    out: dict[str, np.ndarray] = {}
    for key, path in (
        ('done', A.RESEARCH_STAGE_DONE_FILE),
        ('locked', A.RESEARCH_STAGE_LOCKED_FILE),
        ('ready', A.RESEARCH_STAGE_READY_FILE),
    ):
        img = cv2.imread(path)
        if img is None:
            logger.warning('ResearchStage template missing %s path=%s', key, path)
            continue
        if img.shape[0] != 30 or img.shape[1] != 30:
            img = cv2.resize(img, (30, 30), interpolation=cv2.INTER_AREA)
        out[key] = img
    return out


def _combined_score(crop_bgr: np.ndarray, templ_bgr: np.ndarray) -> float:
    """亮度 NCC 0.55 + 均值色相似 0.45（互比对后 RI/RY 交叉约 0.47，自身 1.0）。"""
    a = crop_bgr
    b = templ_bgr
    if a.shape[:2] != (30, 30):
        a = cv2.resize(a, (30, 30), interpolation=cv2.INTER_AREA)
    la = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    la -= float(la.mean())
    lb -= float(lb.mean())
    denom = float(np.linalg.norm(la) * np.linalg.norm(lb)) + 1e-6
    ncc = float(la.ravel() @ lb.ravel()) / denom
    ca = a.reshape(-1, 3).mean(axis=0)
    cb = b.reshape(-1, 3).mean(axis=0)
    dist = float(np.linalg.norm(ca - cb))
    csim = max(0.0, 1.0 - dist / 180.0)
    return 0.55 * ncc + 0.45 * csim


def classify_stage_crop(crop_bgr: np.ndarray) -> tuple[str, float, dict[str, float]]:
    temps = _load_templates()
    if not temps:
        return 'unknown', 0.0, {}
    scores = {k: _combined_score(crop_bgr, t) for k, t in temps.items()}
    best_k = max(scores, key=scores.get)
    best_v = scores[best_k]
    second_v = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
    if best_v < A.RESEARCH_STAGE_SIMILARITY:
        return 'unknown', best_v, scores
    if best_v - second_v < A.RESEARCH_STAGE_MARGIN:
        return 'unknown', best_v, scores
    return best_k, best_v, scores


def stage_slot_area(index_1based: int) -> tuple[int, int, int, int]:
    """1..8 → 30x30 area。"""
    i = int(index_1based) - 1
    cx = int(round(A.RESEARCH_STAGE_FIRST_CENTER[0] + i * A.RESEARCH_STAGE_STEP_X))
    cy = A.RESEARCH_STAGE_FIRST_CENTER[1]
    half = A.RESEARCH_STAGE_HALF
    return cx - half, cy - half, cx + half, cy + half


def scan_research_stages(image) -> list[dict]:
    """
    扫描底栏 8 格。
    Returns:
        [{index, status, score, scores, area}, ...]
    """
    rows: list[dict] = []
    for idx in range(1, A.RESEARCH_STAGE_COUNT + 1):
        area = stage_slot_area(idx)
        x1, y1, x2, y2 = area
        crop = image[y1:y2, x1:x2]
        status, score, scores = classify_stage_crop(crop)
        rows.append({
            'index': idx,
            'status': status,
            'score': round(score, 3),
            'scores': {k: round(v, 3) for k, v in scores.items()},
            'area': area,
            'keyword': A.RESEARCH_STAGE_KEYWORDS[idx - 1],
        })
    logger.info(
        'ResearchStage slots=%s',
        [(r['index'], r['status'], r['score'], r['keyword']) for r in rows],
    )
    return rows
