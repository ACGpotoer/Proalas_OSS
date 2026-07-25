# -*- coding: utf-8 -*-
"""调用内网 AI 规划网关（Bearer planner_token，不上传 LLM Key）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from module.logger import logger
from module.proalas.ai_planner.settings import (
    gateway_health_url,
    gateway_plan_url,
    load_ai_planner_settings,
)


class AiPlannerGatewayError(Exception):
    pass


def _request_json(
    url: str,
    *,
    method: str = 'GET',
    token: str = '',
    body: Optional[dict[str, Any]] = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace') if e.fp else str(e)
        raise AiPlannerGatewayError(f'HTTP {e.code}: {detail}') from e
    except urllib.error.URLError as e:
        raise AiPlannerGatewayError(f'网络错误: {e}') from e
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        raise AiPlannerGatewayError(f'响应非 JSON: {raw[:200]}') from e
    if not isinstance(parsed, dict):
        raise AiPlannerGatewayError('响应格式错误')
    return parsed


def test_gateway_connection() -> dict[str, Any]:
    settings = load_ai_planner_settings(force=True)
    if not settings.configured:
        return {
            'ok': False,
            'error': '未配置 ai_planner.yaml（enabled / gateway_url / planner_token）',
        }
    try:
        resp = _request_json(
            gateway_health_url(settings.gateway_url),
            token=settings.planner_token,
            timeout_sec=min(30, settings.timeout_sec),
        )
        return {
            'ok': bool(resp.get('ok')),
            'gateway': settings.gateway_url,
            'llmConfigured': resp.get('llmConfigured'),
            'rulesVersion': resp.get('rulesVersion'),
            'detail': resp,
        }
    except AiPlannerGatewayError as e:
        logger.warning('AI planner gateway health failed: %s', e)
        return {'ok': False, 'error': str(e), 'gateway': settings.gateway_url}


def request_plan(
    context: dict[str, Any],
    *,
    strategy_id: str = 'conservative',
) -> dict[str, Any]:
    settings = load_ai_planner_settings(force=True)
    if not settings.configured:
        raise AiPlannerGatewayError('未配置 ai_planner.yaml')

    payload = {
        'deviceId': context.get('deviceId'),
        'context': context,
        'strategyId': strategy_id,
        'rulesVersion': settings.rules_version or context.get('rulesVersion'),
    }
    resp = _request_json(
        gateway_plan_url(settings.gateway_url),
        method='POST',
        token=settings.planner_token,
        body=payload,
        timeout_sec=settings.timeout_sec,
    )
    if not resp.get('ok'):
        raise AiPlannerGatewayError(str(resp.get('error') or '网关返回失败'))
    return resp
