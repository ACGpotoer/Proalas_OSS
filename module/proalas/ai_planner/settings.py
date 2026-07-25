# -*- coding: utf-8 -*-
"""AI 规划客户端配置：mumucontrol/ai_planner.yaml（LLM Key 不在此文件）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

_ALAS_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_YAML_CANDIDATES = (
    _ALAS_ROOT / 'dap_data' / 'ai_planner.yaml',
    _ALAS_ROOT / 'config' / 'proalas' / 'ai_planner.yaml',
    _ALAS_ROOT / 'mumucontrol' / 'ai_planner.yaml',
)
_DEFAULT_YAML = next((p for p in _DEFAULT_YAML_CANDIDATES if p.is_file()), _DEFAULT_YAML_CANDIDATES[0])
_settings_cache: tuple[float, 'AiPlannerClientSettings'] | None = None


@dataclass(frozen=True)
class AiPlannerClientSettings:
    enabled: bool = False
    gateway_url: str = ''
    planner_token: str = ''
    rules_version: str = ''
    timeout_sec: int = 120
    stale_collector_hours: int = 6

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.gateway_url.strip() and self.planner_token.strip())


def _alas_root() -> Path:
    return _ALAS_ROOT


def ai_planner_yaml_path() -> str:
    return str(_DEFAULT_YAML)


def _load_yaml_raw() -> dict[str, Any]:
    path = _DEFAULT_YAML
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_ai_planner_settings(*, force: bool = False) -> AiPlannerClientSettings:
    global _settings_cache
    path = _DEFAULT_YAML
    try:
        mtime = path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        mtime = 0.0
    if not force and _settings_cache is not None and _settings_cache[0] == mtime:
        return _settings_cache[1]

    raw = _load_yaml_raw()
    block = raw.get('ai_planner') if isinstance(raw.get('ai_planner'), dict) else raw

    def _pick(key: str, env: str, default: Any) -> Any:
        val = os.environ.get(env)
        if val is not None and str(val).strip() != '':
            return val
        if isinstance(block, dict) and key in block:
            return block[key]
        return default

    settings = AiPlannerClientSettings(
        enabled=bool(_pick('enabled', 'AI_PLANNER_ENABLED', False)),
        gateway_url=str(_pick('gateway_url', 'AI_PLANNER_GATEWAY_URL', '') or '').strip().rstrip('/'),
        planner_token=str(_pick('planner_token', 'AI_PLANNER_TOKEN', '') or '').strip(),
        rules_version=str(_pick('rules_version', 'AI_PLANNER_RULES_VERSION', '') or '').strip(),
        timeout_sec=int(_pick('timeout_sec', 'AI_PLANNER_TIMEOUT_SEC', 120) or 120),
        stale_collector_hours=int(_pick('stale_collector_hours', 'AI_PLANNER_STALE_HOURS', 6) or 6),
    )
    _settings_cache = (mtime, settings)
    return settings


def gateway_health_url(base_url: str) -> str:
    return f'{base_url.rstrip("/")}/v1/health'


def gateway_plan_url(base_url: str) -> str:
    return f'{base_url.rstrip("/")}/v1/plan'
