# -*- coding: utf-8 -*-
"""ProAlas 扩展 WebUI 页面（资源统计折线图等）。"""
from __future__ import annotations

import json

from pywebio.output import put_html

from module.logger import logger
from module.proalas.resource_history import (
    build_resource_series,
    chart_series_percent,
    current_snapshot_from_userdata,
)

CHART_META = [
    ('oil', '石油', 'ProalasResourceStats_ChartOil'),
    ('money', '物资', 'ProalasResourceStats_ChartMoney'),
    ('cube', '魔方', 'ProalasResourceStats_ChartCube'),
    ('act_pt', '活动 PT', 'ProalasResourceStats_ChartActPt'),
    ('rmb', '钻石', 'ProalasResourceStats_ChartRmb'),
    ('boat_rate', '收藏率', 'ProalasResourceStats_ChartBoatRate'),
    ('boat_max', '船坞上限', 'ProalasResourceStats_ChartBoatMax'),
]

CHART_COLORS = {
    'oil': '#f59e0b', 'money': '#eab308', 'cube': '#818cf8',
    'act_pt': '#f472b6', 'rmb': '#38bdf8', 'boat_rate': '#34d399',
    'boat_max': '#94a3b8',
}

# 浅色面板（Alas WebUI 默认浅底；勿用 #1b2232 整块铺底）
PA_LIGHT_CSS = """
.pa-proalas-hero {
  background: linear-gradient(135deg, rgba(56,189,248,.10) 0%, rgba(99,102,241,.08) 100%);
  border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 14px 16px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}
.pa-proalas-hero h4 {
  margin: 0 0 6px; font-size: 15px; font-weight: 700; color: #1e293b;
}
.pa-proalas-hero p { margin: 0; font-size: 12px; color: #64748b; line-height: 1.55; }
.pa-proalas-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 14px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
  gap: 0 !important;
}
.pa-proalas-card > * { margin: 0 !important; }
.pa-proalas-card .markdown-body, .pa-proalas-card .markdown-body > * {
  margin: 0 !important; padding: 0 !important;
}
.pa-cfg-row {
  display: flex; justify-content: space-between; align-items: center;
  gap: 12px; padding: 8px 0 !important; margin: 0 !important;
  border-bottom: 1px solid #f1f5f9;
  min-height: 0 !important;
}
.pa-cfg-row:last-child { border-bottom: none; padding-bottom: 2px !important; }
.pa-cfg-label { flex: 1 1 auto; min-width: 0; line-height: 1.45; }
.pa-cfg-label strong { display: block; font-size: 13px; color: #1e293b; font-weight: 600; }
.pa-cfg-hint { display: block; font-size: 11px; color: #94a3b8; margin-top: 2px; }
.pa-cfg-row > :last-child {
  flex: 0 0 auto; display: flex; align-items: center; justify-content: flex-end;
  min-width: 0; max-width: 200px; margin: 0 !important;
}
.pa-cfg-row > :last-child [class*="arg_container"] { margin: 0 !important; padding: 0 !important; }
.pa-cfg-row > :last-child .--arg-title--,
.pa-cfg-row > :last-child [style*="--arg-title--"] {
  display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important;
}
.pa-cfg-row > :last-child .form-control {
  border-radius: 8px !important; font-size: 12px !important;
  border-color: #cbd5e1 !important; background: #f8fafc !important;
  min-height: 32px !important; padding: 4px 10px !important;
}
.pa-cfg-row > :last-child .pywebio-row { margin: 0 !important; padding: 0 !important; }
.pa-cfg-control {
  flex: 0 0 auto; display: flex; align-items: center; justify-content: flex-end;
  min-width: 0; max-width: 200px;
}
.pa-cfg-control [class*="arg_container"] { margin: 0 !important; padding: 0 !important; }
.pa-cfg-control .--arg-title--,
.pa-cfg-control [style*="--arg-title--"] {
  display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important;
}
.pa-cfg-control .form-control {
  border-radius: 8px !important; font-size: 12px !important;
  border-color: #cbd5e1 !important; background: #f8fafc !important;
  min-height: 32px !important; padding: 4px 10px !important;
}
.pa-cfg-control .pywebio-row { margin: 0 !important; padding: 0 !important; }
"""


def _pa_i18n_text(group_name: str, arg_name: str, field: str, *, fallback: str = '') -> str:
    from module.webui.lang import t

    text = t(f'{group_name}.{arg_name}.{field}')
    key = f'{group_name}.{arg_name}.{field}'
    if not text or text == key or text.startswith(group_name + '.'):
        return fallback
    return text


def _pa_config_row(
    task: str,
    group_name: str,
    arg_name: str,
    arg_dict: dict,
    config_data: dict,
    *,
    scope_prefix: str = 'pa',
):
    from html import escape

    from pywebio.output import put_html, put_row, use_scope

    label = _pa_i18n_text(group_name, arg_name, 'name', fallback=arg_name)
    hint = _pa_i18n_text(group_name, arg_name, 'help')
    if not arg_dict or 'type' not in arg_dict:
        logger.warning(
            'ProAlas UI skip widget %s.%s: missing args.json entry (run config_updater)',
            group_name,
            arg_name,
        )
        return None
    with use_scope(f'{scope_prefix}_{task}_{arg_name}'):
        w = _put_task_widget(
            task, group_name, arg_name, arg_dict, config_data,
            compact=True, hide_title=True,
        )
    if w is None:
        return None
    hint_html = f'<span class="pa-cfg-hint">{escape(hint)}</span>' if hint else ''
    return put_row([
        put_html(f'<div class="pa-cfg-label"><strong>{escape(label)}</strong>{hint_html}</div>'),
        w,
    ], size='1fr auto').style('pa-cfg-row')


def _hex_rgba(hex_color: str, alpha: float = 0.12) -> str:
    h = str(hex_color or '').lstrip('#')
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f'rgba({r},{g},{b},{alpha})'
    return f'rgba(148,163,184,{alpha})'


def _enabled_charts(config) -> list[tuple[str, str, str]]:
    out = []
    for key, label, attr in CHART_META:
        if getattr(config, attr, True):
            out.append((key, label, attr))
    return out


def _fmt_rs_value(key: str, val) -> str:
    if key == 'boat_rate' and isinstance(val, (int, float)):
        v = float(val)
        if v <= 0:
            return '0%'
        if v <= 1.5:
            v *= 100
        return f'{round(v, 1)}%'
    return str(val)


def _snap_rs_numeric(key: str, snap: dict) -> float | None:
    val = snap.get(key)
    if val is None or val == '—':
        return None
    if key == 'boat_rate':
        try:
            v = float(val)
        except (TypeError, ValueError):
            return None
        if v <= 0:
            return 0.0
        return v * 100 if v <= 1.5 else v
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _rs_last_n_day_labels(n: int = 7) -> list[str]:
    from datetime import date, timedelta

    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _rs_short_label(text: str) -> str:
    text = str(text or '')
    if len(text) >= 10 and text[4] == '-' and text[7] == '-':
        return text[5:10]
    if len(text) > 8:
        return text[-8:]
    return text


def _build_rs_line_svg(
    points: list[dict],
    *,
    snap_numeric: float | None,
    color: str,
    width: int = 520,
    height: int = 150,
) -> tuple[str, bool]:
    """纯 SVG 折线（不依赖 Chart.js / put_html 内联 script）。"""
    from html import escape

    pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 24
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b

    if points:
        labels = [str(p.get('t', '')) for p in points]
        data: list[float | None] = []
        for p in points:
            v = p.get('v')
            if v is None:
                data.append(None)
            else:
                try:
                    data.append(float(v))
                except (TypeError, ValueError):
                    data.append(None)
        sparse = False
    else:
        labels = _rs_last_n_day_labels(7)
        if snap_numeric is not None:
            data = [snap_numeric] * len(labels)
        else:
            data = [0.0] * len(labels)
        sparse = True

    nums = [v for v in data if v is not None]
    if not nums:
        vmin, vmax = 0.0, 1.0
    else:
        vmin = min(0.0, min(nums))
        vmax = max(nums)
        if vmax <= vmin:
            vmax = vmin + 1.0

    def x_pos(i: int) -> float:
        if len(labels) <= 1:
            return pad_l + inner_w / 2
        return pad_l + (inner_w * i / (len(labels) - 1))

    def y_pos(v: float) -> float:
        return pad_t + inner_h - (inner_h * (v - vmin) / (vmax - vmin))

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'class="pa-rs-svg" xmlns="http://www.w3.org/2000/svg" role="img">',
        f'<rect width="{width}" height="{height}" fill="#fafbfc" rx="6"/>',
    ]

    for i in range(4):
        gy = pad_t + inner_h * i / 3
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#f1f5f9" stroke-width="1"/>'
        )

    last_xy: tuple[float, float] | None = None
    for i, v in enumerate(data):
        if v is None:
            continue
        x, y = x_pos(i), y_pos(v)
        if last_xy is not None:
            parts.append(
                f'<line x1="{last_xy[0]:.1f}" y1="{last_xy[1]:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                f'stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
            )
        last_xy = (x, y)

    if last_xy is not None:
        parts.append(
            f'<circle cx="{last_xy[0]:.1f}" cy="{last_xy[1]:.1f}" r="{3.5 if sparse else 2.5}" fill="{color}"/>'
        )

    if labels:
        tick_idx = sorted({0, len(labels) // 2, len(labels) - 1})
        for idx in tick_idx:
            lx = x_pos(idx)
            lbl = escape(_rs_short_label(labels[idx]))
            parts.append(
                f'<text x="{lx:.1f}" y="{height - 6}" text-anchor="middle" '
                f'font-size="9" fill="#94a3b8">{lbl}</text>'
            )

    if nums:
        parts.append(
            f'<text x="{pad_l - 4}" y="{y_pos(vmax):.1f}" text-anchor="end" '
            f'font-size="8" fill="#94a3b8">{escape(str(round(vmax, 1)))}</text>'
        )
        if vmin != vmax:
            parts.append(
                f'<text x="{pad_l - 4}" y="{y_pos(vmin):.1f}" text-anchor="end" '
                f'font-size="8" fill="#94a3b8">{escape(str(round(vmin, 1)))}</text>'
            )

    parts.append('</svg>')
    return ''.join(parts), sparse


def _init_resource_stats_chart_js(
    series_payload: dict,
    snap_payload: dict,
    default_key: str,
    labels: dict[str, str],
) -> None:
    """PyWebIO put_html 内联 script 不执行，用 run_js 绑定下拉与表格切换。"""
    from pywebio.session import run_js

    run_js(
        """
        (function () {
          var board = document.getElementById('pa-rs-board');
          if (!board || board._paRsReady) return;
          board._paRsReady = true;

          var SERIES = series;
          var SNAP = snap;
          var COLORS = colors;
          var LABELS = labels;
          var defaultKey = defaultKeyArg;

          function hexEsc(s) { return String(s || '').replace(/[&<>"]/g, function (c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
          }); }

          function lastNDays(n) {
            var out = [], d = new Date();
            for (var i = n - 1; i >= 0; i--) {
              var t = new Date(d);
              t.setDate(t.getDate() - i);
              out.push(t.toISOString().slice(0, 10));
            }
            return out;
          }

          function shortLabel(text) {
            text = String(text || '');
            if (text.length >= 10 && text[4] === '-' && text[7] === '-') return text.slice(5, 10);
            if (text.length > 8) return text.slice(-8);
            return text;
          }

          function snapNumeric(key) {
            var raw = SNAP[key];
            if (raw == null || raw === '—') return null;
            if (typeof raw === 'string' && raw.indexOf('%') >= 0) {
              var p = parseFloat(raw);
              return isNaN(p) ? null : p;
            }
            var v = Number(raw);
            return isNaN(v) ? null : v;
          }

          function buildSvg(key) {
            var color = COLORS[key] || '#94a3b8';
            var pts = SERIES[key] || [];
            var snapVal = snapNumeric(key);
            var width = 520, height = 150;
            var padL = 40, padR = 10, padT = 10, padB = 24;
            var innerW = width - padL - padR;
            var innerH = height - padT - padB;
            var labels, data, sparse;

            if (pts.length) {
              labels = pts.map(function (p) { return String(p.t || ''); });
              data = pts.map(function (p) {
                var v = Number(p.v);
                return isNaN(v) ? null : v;
              });
              sparse = false;
            } else {
              labels = lastNDays(7);
              data = labels.map(function () { return snapVal != null ? snapVal : 0; });
              sparse = true;
            }

            var nums = data.filter(function (v) { return v != null; });
            var vmin = 0, vmax = 1;
            if (nums.length) {
              vmin = Math.min(0, Math.min.apply(null, nums));
              vmax = Math.max.apply(null, nums);
              if (vmax <= vmin) vmax = vmin + 1;
            }

            function xPos(i) {
              if (labels.length <= 1) return padL + innerW / 2;
              return padL + innerW * i / (labels.length - 1);
            }
            function yPos(v) {
              return padT + innerH - innerH * (v - vmin) / (vmax - vmin);
            }

            var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" width="100%" height="' + height + '" class="pa-rs-svg" xmlns="http://www.w3.org/2000/svg">';
            svg += '<rect width="' + width + '" height="' + height + '" fill="#fafbfc" rx="6"/>';
            for (var gi = 0; gi < 4; gi++) {
              var gy = padT + innerH * gi / 3;
              svg += '<line x1="' + padL + '" y1="' + gy + '" x2="' + (width - padR) + '" y2="' + gy + '" stroke="#f1f5f9" stroke-width="1"/>';
            }

            var last = null;
            for (var i = 0; i < data.length; i++) {
              var v = data[i];
              if (v == null) continue;
              var x = xPos(i), y = yPos(v);
              if (last) {
                svg += '<line x1="' + last[0] + '" y1="' + last[1] + '" x2="' + x + '" y2="' + y + '" stroke="' + color + '" stroke-width="2"/>';
              }
              last = [x, y];
            }
            if (last) {
              svg += '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="' + (sparse ? 3.5 : 2.5) + '" fill="' + color + '"/>';
            }

            var ticks = [0, Math.floor(labels.length / 2), labels.length - 1];
            ticks.forEach(function (idx) {
              if (idx < 0 || idx >= labels.length) return;
              svg += '<text x="' + xPos(idx) + '" y="' + (height - 6) + '" text-anchor="middle" font-size="9" fill="#94a3b8">' + hexEsc(shortLabel(labels[idx])) + '</text>';
            });
            svg += '</svg>';
            return { svg: svg, sparse: sparse };
          }

          function render(key) {
            var built = buildSvg(key);
            var inner = document.getElementById('pa-rs-chart-inner');
            var nowEl = document.getElementById('pa-rs-now-val');
            var hint = document.getElementById('pa-rs-no-hist');
            if (inner) inner.innerHTML = built.svg;
            if (nowEl) nowEl.textContent = SNAP[key] != null ? SNAP[key] : '—';
            if (hint) hint.style.display = built.sparse ? 'block' : 'none';
            document.querySelectorAll('#pa-rs-table tbody tr').forEach(function (tr) {
              tr.classList.toggle('pa-rs-row-active', tr.getAttribute('data-rs-key') === key);
            });
          }

          var sel = document.getElementById('pa-rs-select');
          if (sel) {
            sel.addEventListener('change', function () { render(sel.value); });
          }
          document.querySelectorAll('#pa-rs-table tbody tr').forEach(function (tr) {
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', function () {
              var k = tr.getAttribute('data-rs-key');
              if (!k || !sel) return;
              sel.value = k;
              render(k);
            });
          });
          render(sel ? (sel.value || defaultKey) : defaultKey);
        })();
        """,
        series=series_payload,
        snap=snap_payload,
        colors=CHART_COLORS,
        labels=labels,
        defaultKeyArg=default_key,
    )


def render_resource_stats_dashboard(config, device_id: str) -> None:
    log_dir = getattr(config, 'ProalasResourceStats_AlasLogPath', '') or None
    series = chart_series_percent(build_resource_series(device_id, log_dir))
    snap = current_snapshot_from_userdata(device_id, log_dir=log_dir)

    enabled = _enabled_charts(config)
    if not enabled:
        enabled = [(k, lbl, attr) for k, lbl, attr in CHART_META]

    chart_options = []
    series_payload: dict[str, list] = {}
    snap_payload: dict[str, str] = {}
    for k, label, _ in enabled:
        chart_options.append(f'<option value="{k}">{label}</option>')
        series_payload[k] = series.get(k) or []
        snap_payload[k] = _fmt_rs_value(k, snap.get(k, '—'))

    default_key = enabled[0][0] if enabled else 'oil'
    initial_svg, initial_sparse = _build_rs_line_svg(
        series_payload.get(default_key) or [],
        snap_numeric=_snap_rs_numeric(default_key, snap),
        color=CHART_COLORS.get(default_key, '#94a3b8'),
    )
    sparse_style = '' if initial_sparse else 'display:none'

    table_rows = []
    for i, (k, label, _) in enumerate(enabled):
        v = snap_payload.get(k, '—')
        n = len(series.get(k) or [])
        dot = CHART_COLORS.get(k, '#94a3b8')
        row_cls = 'pa-rs-row-active' if k == default_key else ''
        table_rows.append(
            f'<tr class="{row_cls}" data-rs-key="{k}">'
            f'<td><span class="pa-rs-dot" style="background:{dot}"></span>{label}</td>'
            f'<td class="pa-rs-td-val">{v}</td><td>{n}</td></tr>'
        )

    series_json = json.dumps(series_payload, ensure_ascii=False)
    snap_json = json.dumps(snap_payload, ensure_ascii=False)
    from html import escape

    series_attr = escape(series_json, quote=True)
    snap_attr = escape(snap_json, quote=True)
    labels_for_js = {k: lbl for k, lbl, _ in enabled}

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-rs-board {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0 0 10px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-rs-toolbar {{
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  flex-wrap: wrap; margin-bottom: 8px;
}}
.pa-rs-select-wrap {{ display: flex; align-items: center; gap: 8px; flex: 1 1 auto; min-width: 0; }}
.pa-rs-select-label {{ font-size: 12px; font-weight: 600; color: #64748b; white-space: nowrap; }}
.pa-rs-select {{
  flex: 1 1 auto; max-width: 200px; border-radius: 8px; border: 1px solid #cbd5e1;
  font-size: 12px; padding: 5px 10px; min-height: 32px; background: #f8fafc; color: #334155;
}}
.pa-rs-now {{
  font-size: 13px; font-weight: 700; color: #1e293b;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}}
.pa-rs-now span {{ font-size: 11px; font-weight: 600; color: #94a3b8; margin-right: 4px; }}
.pa-rs-chart-box {{ min-height: 150px; position: relative; min-width: 0; }}
.pa-rs-chart-inner {{ width: 100%; min-height: 150px; }}
.pa-rs-svg {{ display: block; width: 100%; height: 150px; }}
.pa-rs-no-hist {{
  position: absolute; right: 8px; bottom: 6px; font-size: 10px; color: #94a3b8;
  pointer-events: none;
}}
.pa-rs-body {{ display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 10px; align-items: start; }}
.pa-rs-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 5px; vertical-align: middle; }}
.pa-rs-table-title {{ margin: 0 0 6px; font-size: 12px; font-weight: 600; color: #1e293b; }}
.pa-rs-table-foot {{ margin: 6px 0 0; font-size: 10px; color: #94a3b8; line-height: 1.4; }}
.pa-rs-table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
.pa-rs-table th {{
  padding: 4px 6px; text-align: left; color: #64748b; font-weight: 600;
  border-bottom: 1px solid #e2e8f0; background: #f8fafc;
}}
.pa-rs-table td {{ padding: 4px 6px; border-bottom: 1px solid #f1f5f9; color: #334155; }}
.pa-rs-table tr:last-child td {{ border-bottom: none; }}
.pa-rs-table tr.pa-rs-row-active {{ background: #f0f9ff; }}
.pa-rs-td-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
@media (max-width: 768px) {{
  .pa-rs-body {{ grid-template-columns: 1fr; }}
}}
</style>
<div class="pa-proalas-hero" style="padding:10px 14px;margin-bottom:8px">
  <h4 style="margin-bottom:4px">资源趋势</h4>
  <p>下拉切换资源折线图；缺省日期以直线连接。数据：ProalasData.ResourceHistory（近 30 日）。</p>
</div>
<div class="pa-rs-board" id="pa-rs-board"
     data-series="{series_attr}" data-snap="{snap_attr}">
  <div class="pa-rs-toolbar">
    <div class="pa-rs-select-wrap">
      <span class="pa-rs-select-label">资源</span>
      <select class="pa-rs-select" id="pa-rs-select">{''.join(chart_options)}</select>
    </div>
    <div class="pa-rs-now" id="pa-rs-now">
      <span>当前</span><strong id="pa-rs-now-val">{snap_payload.get(default_key, '—')}</strong>
    </div>
  </div>
  <div class="pa-rs-body">
    <div class="pa-rs-chart-box">
      <div class="pa-rs-chart-inner" id="pa-rs-chart-inner">{initial_svg}</div>
      <span class="pa-rs-no-hist" id="pa-rs-no-hist" style="{sparse_style}">无历史点，已用当前值平线占位</span>
    </div>
    <div class="pa-rs-table-wrap">
      <h4 class="pa-rs-table-title">快照 / 点数</h4>
      <table class="pa-rs-table" id="pa-rs-table">
        <thead><tr><th>资源</th><th>当前</th><th>点</th></tr></thead>
        <tbody>{''.join(table_rows)}</tbody>
      </table>
      <p class="pa-rs-table-foot">快照 {snap.get('synced_at') or '—'}</p>
    </div>
  </div>
</div>
        """
    )
    _init_resource_stats_chart_js(series_payload, snap_payload, default_key, labels_for_js)


def render_resource_stats_config_panel(config, task_args: dict, *, device_id: str = '') -> None:
    """资源统计配置：数据说明 + 日志路径 + 折线图开关。"""
    from html import escape

    from module.config.deep import deep_iter
    from module.config.utils import filepath_config
    from pywebio.output import put_column, put_html, put_row

    task = 'ProalasResourceStats'
    group_name = 'ProalasResourceStats'
    group_args = {arg[0]: arg_dict for arg, arg_dict in deep_iter(task_args.get(group_name, {}), depth=1)}
    config_data = config.data if hasattr(config, 'data') else config
    cfg_name = str(device_id or getattr(config, 'config_name', '') or 'alas')
    cfg_path = filepath_config(cfg_name)

    path_fields = ('AlasLogPath',)
    chart_fields = (
        'ChartOil', 'ChartMoney', 'ChartCube', 'ChartActPt',
        'ChartRmb', 'ChartBoatRate', 'ChartBoatMax',
    )

    path_rows = []
    for arg_name in path_fields:
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        row = _pa_config_row(task, group_name, arg_name, arg_dict, config_data, scope_prefix='rs')
        if row is not None:
            path_rows.append(row)

    chart_rows = []
    for arg_name in chart_fields:
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        row = _pa_config_row(task, group_name, arg_name, arg_dict, config_data, scope_prefix='rs')
        if row is not None:
            chart_rows.append(row)

    mid = (len(chart_rows) + 1) // 2
    left_charts = chart_rows[:mid]
    right_charts = chart_rows[mid:]

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-rs-cfg-board {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0 0 10px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-rs-cfg-title {{
  margin: 0 0 8px; font-size: 13px; font-weight: 700; color: #1e293b;
}}
.pa-rs-cfg-sub {{
  margin: 10px 0 6px; font-size: 12px; font-weight: 600; color: #64748b;
}}
.pa-rs-data-src {{
  margin: 0 0 10px; padding: 8px 10px;
  border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc;
  font-size: 11px; line-height: 1.55; color: #475569;
}}
.pa-rs-data-src p {{ margin: 0 0 6px; }}
.pa-rs-data-src p:last-child {{ margin-bottom: 0; }}
.pa-rs-data-src-k {{
  display: inline-block; min-width: 36px; font-weight: 700; color: #64748b;
}}
.pa-rs-data-src code {{
  font-size: 10px; background: #fff; padding: 1px 4px; border-radius: 4px;
  border: 1px solid #e2e8f0;
}}
.pa-rs-data-src-note {{ color: #94a3b8; font-size: 10px; }}
.pa-rs-cfg-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }}
scope.pa-rs-cfg-grid {{
  display: grid !important; grid-template-columns: 1fr 1fr !important; gap: 0 14px !important;
}}
.pa-rs-cfg-col {{ display: flex; flex-direction: column; gap: 0 !important; }}
scope.pa-rs-cfg-col > * {{ margin: 0 !important; }}
@media (max-width: 640px) {{
  .pa-rs-cfg-grid, scope.pa-rs-cfg-grid {{ grid-template-columns: 1fr !important; }}
}}
</style>
<div class="pa-rs-cfg-board">
  <h4 class="pa-rs-cfg-title">配置</h4>
        """
    )

    if path_rows:
        put_html('<p class="pa-rs-cfg-sub">数据路径</p>')
        put_html(
            f'<div class="pa-rs-data-src">'
            f'<p><span class="pa-rs-data-src-k">快照</span>'
            f'<code>{escape(cfg_path)}</code> → <code>ProalasData.GameResource</code></p>'
            f'<p><span class="pa-rs-data-src-k">时序</span>'
            f'<code>ProalasData.ResourceHistory</code>；不足时回退解析 Alas 日志</p>'
            f'<p class="pa-rs-data-src-note">已嵌入原生 Alas，不再使用 ProAlas/data/UserData.json</p>'
            f'</div>'
        )
        put_column(path_rows).style('pa-proalas-card pa-rs-cfg-paths')

    if chart_rows:
        put_html('<p class="pa-rs-cfg-sub">折线图显示开关</p>')
        cols = []
        if left_charts:
            cols.append(put_column(left_charts).style('pa-rs-cfg-col'))
        if right_charts:
            cols.append(put_column(right_charts).style('pa-rs-cfg-col'))
        if cols:
            put_row(cols, size='1fr 1fr').style('pa-rs-cfg-grid')

    put_html('</div>')


def render_account_screen_monitor(device_id: str, refresh_sec: int = 5) -> None:
    from module.proalas.screen_paths import (
        LATEST_NAME,
        img_url,
        list_screenshot_files,
        latest_screenshot_path,
    )

    shots = list_screenshot_files(device_id, limit=10)
    latest = latest_screenshot_path(device_id)
    latest_name = LATEST_NAME if latest and latest.name == LATEST_NAME else (shots[0] if shots else '')
    has_image = bool(latest_name)

    if has_image:
        main_src = img_url(device_id, latest_name)
        main_html = (
            f'<img id="pa-am-main" class="pa-am-main" src="{main_src}" '
            f'alt="设备截图" />'
        )
    else:
        main_html = (
            '<div class="pa-am-empty">暂无截图。请启用 Scheduler、启动 Alas 调度，'
            '或清空「下一次运行时间」立即执行一次；成功后刷新本页，预览在下方。</div>'
        )

    thumb_items = []
    for name in shots:
        src = img_url(device_id, name)
        active = ' pa-am-thumb-active' if name == latest_name else ''
        thumb_items.append(
            f'<button type="button" class="pa-am-thumb{active}" data-src="{src}" '
            f'data-name="{name}" title="{name}">'
            f'<img src="{src}" alt="{name}" loading="lazy" /></button>'
        )
    thumbs_html = ''.join(thumb_items) if thumb_items else '<span class="pa-am-no-thumbs">—</span>'

    refresh_ms = max(3000, int(refresh_sec) * 1000)
    device_js = json.dumps(str(device_id))
    latest_js = json.dumps(latest_name)

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-am-wrap {{
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 14px;
  margin: 0 0 16px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-am-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 10px; gap: 12px; flex-wrap: wrap;
}}
.pa-am-head h4 {{ margin: 0; font-size: 14px; font-weight: 600; color: #1e293b; }}
.pa-am-meta {{ font-size: 11px; color: #64748b; }}
.pa-am-stage {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  min-height: 180px;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}}
.pa-am-main {{ max-width: 100%; max-height: 420px; display: block; }}
.pa-am-empty {{ padding: 28px 16px; font-size: 12px; color: #64748b; text-align: center; }}
.pa-am-thumbs {{
  display: flex; gap: 8px; margin-top: 10px; overflow-x: auto; padding-bottom: 4px;
}}
.pa-am-thumb {{
  border: 1px solid #e2e8f0; border-radius: 6px; padding: 0;
  background: #fff; cursor: pointer; flex: 0 0 auto; width: 96px; height: 54px;
  overflow: hidden;
}}
.pa-am-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.pa-am-thumb-active {{ border-color: #6366f1; box-shadow: 0 0 0 1px rgba(99,102,241,.35); }}
.pa-am-no-thumbs {{ font-size: 11px; color: #94a3b8; }}
</style>
<div class="pa-am-wrap" id="pa-am-wrap">
  <div class="pa-am-head">
    <h4 id="pa-am-preview">实时截图监控</h4>
    <span class="pa-am-meta">img/{device_id}/ · 每 {refresh_sec}s 刷新 · 保留最近 10 张</span>
  </div>
  <div class="pa-am-stage">{main_html}</div>
  <div class="pa-am-thumbs" id="pa-am-thumbs">{thumbs_html}</div>
</div>
<script>
(function() {{
  var deviceId = {device_js};
  var latestName = {latest_js};
  var refreshMs = {refresh_ms};

  function imgUrl(name) {{
    var base = window.location.origin || '';
    return base + '/img/' + encodeURIComponent(deviceId) + '/' + encodeURIComponent(name);
  }}

  function bust(url) {{
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + 't=' + Date.now();
  }}

  function refreshMain(forceName) {{
    var img = document.getElementById('pa-am-main');
    if (!img) return;
    var name = forceName || latestName || 'latest.png';
    img.src = bust(imgUrl(name));
  }}

  document.querySelectorAll('.pa-am-thumb').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      document.querySelectorAll('.pa-am-thumb').forEach(function(el) {{
        el.classList.remove('pa-am-thumb-active');
      }});
      btn.classList.add('pa-am-thumb-active');
      var img = document.getElementById('pa-am-main');
      if (!img) return;
      var name = btn.getAttribute('data-name') || '';
      if (img && name) img.src = bust(imgUrl(name));
    }});
  }});

  if (document.getElementById('pa-am-main')) {{
    setInterval(function() {{ refreshMain(); }}, refreshMs);
  }}
}})();
</script>
        """
    )


def _put_task_widget(
    task: str,
    group_name: str,
    arg_name: str,
    arg_dict: dict,
    config: dict,
    *,
    compact: bool = False,
    hide_title: bool = False,
):
    """Render a single config widget (same naming as app.set_group)."""
    from datetime import datetime

    from module.config.deep import deep_get
    from module.webui.lang import t
    from module.webui.widgets import put_output

    output_kwargs = arg_dict.copy()
    display = output_kwargs.pop('display', None)
    if display == 'hide':
        return None
    if display == 'disabled':
        output_kwargs['disabled'] = True
    output_kwargs['widget_type'] = output_kwargs.pop('type')
    output_kwargs['name'] = f'{task}_{group_name}_{arg_name}'
    if compact and hide_title:
        output_kwargs['title'] = ''
    elif compact:
        output_kwargs['title'] = t(f'{group_name}.{arg_name}.short') or t(f'{group_name}.{arg_name}.name')
    else:
        output_kwargs['title'] = t(f'{group_name}.{arg_name}.name')
    value = deep_get(config, [task, group_name, arg_name], output_kwargs['value'])
    value = str(value) if isinstance(value, datetime) else value
    output_kwargs['value'] = value
    options = output_kwargs.pop('option', [])
    output_kwargs['options'] = options
    options_label = [t(f'{group_name}.{arg_name}.{opt}') for opt in options]
    output_kwargs['options_label'] = options_label
    if compact:
        output_kwargs['help'] = None
    else:
        arg_help = t(f'{group_name}.{arg_name}.help')
        output_kwargs['help'] = arg_help if arg_help else None
    output_kwargs['invalid_feedback'] = t('Gui.Text.InvalidFeedBack', value)
    return put_output(output_kwargs)


def render_auto_equip_panel(config, task_args: dict) -> None:
    """自动换装备和配置装备：五档策略设置。"""
    from module.config.deep import deep_iter
    from pywebio.output import put_column, put_html

    task = 'ProalasAutoEquip'
    group_name = 'ProalasAutoEquip'
    group_args = {arg[0]: arg_dict for arg, arg_dict in deep_iter(task_args.get(group_name, {}), depth=1)}
    config_data = config.data if hasattr(config, 'data') else config

    put_html(
        f"""
<style>{PA_LIGHT_CSS}</style>
<div class="pa-proalas-hero">
  <h4>装备补齐策略</h4>
  <p>按指定编队逐舰扫描空槽并自动补齐；可与<strong>自动更换队伍</strong>联动。Scheduler 开关见下方调度组。</p>
</div>
        """
    )

    field_order = (
        'TeamNo',
        'EquipQuality',
        'ReplaceSurplusPurple',
        'AllowCraft',
        'CraftCoinLimit',
        'WarehouseReserve',
    )
    rows = []
    for arg_name in field_order:
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        row = _pa_config_row(task, group_name, arg_name, arg_dict, config_data, scope_prefix='ae')
        if row is not None:
            rows.append(row)

    if rows:
        put_column(rows).style('pa-proalas-card')


def render_auto_exp_book_panel(config, task_args: dict) -> None:
    """自动使用经验书：品质/轮数配置 + 上次运行状态。"""
    from html import escape

    from module.config.deep import deep_iter
    from module.proalas_collector.userdata import read_auto_exp_book_status
    from pywebio.output import put_column, put_html

    task = 'ProalasAutoExpBook'
    group_name = 'ProalasAutoExpBook'
    group_args = {arg[0]: arg_dict for arg, arg_dict in deep_iter(task_args.get(group_name, {}), depth=1)}
    config_data = config.data if hasattr(config, 'data') else config
    config_name = str(getattr(config, 'config_name', '') or 'alas')
    snap = read_auto_exp_book_status(config_name)
    status = str(snap.get('status') or 'idle')
    status_label = str(snap.get('statusLabel') or '尚未运行')
    last_run = str(snap.get('lastRunAt') or '—')
    rounds_done = snap.get('feedRoundsDone', '—')
    rounds_target = snap.get('feedRoundsTarget', '—')
    status_cls = {
        'ok': 'pa-tt-on',
        'empty_dock': 'pa-tt-off',
        'partial': 'pa-tt-off',
        'nav_failed': 'pa-tt-off',
        'filter_failed': 'pa-tt-off',
    }.get(status, 'muted')

    put_html(
        f"""
<style>{PA_LIGHT_CSS}</style>
<div class="pa-proalas-hero">
  <h4>经验书喂食</h4>
  <p>主界面 → 船坞 → 筛选<strong>全部 / 全阵营 / 品质 / 未满级</strong>后自动选船喂食；空列表时停止并显示状态。</p>
</div>
<div class="pa-proalas-card" style="margin-bottom:12px;">
  <p style="margin:0 0 6px;font-size:12px;color:#64748b;">上次运行</p>
  <p style="margin:0 0 4px;"><strong class="{status_cls}">{escape(status_label)}</strong></p>
  <p style="margin:0;font-size:12px;color:#64748b;">
    时间 {escape(last_run)} · 轮次 {escape(str(rounds_done))}/{escape(str(rounds_target))}
  </p>
</div>
        """
    )

    field_order = ('ShipRarity', 'FeedRoundsPerRun', 'RunIntervalDays')
    rows = []
    for arg_name in field_order:
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        row = _pa_config_row(task, group_name, arg_name, arg_dict, config_data, scope_prefix='aeb')
        if row is not None:
            rows.append(row)

    if rows:
        put_column(rows).style('pa-proalas-card')


def render_smart_dispatch_panel(config, task_args: dict) -> None:
    """智能资源调度：总开关 + 互斥资源偏好开关 + 说明文案。"""
    import json as json_mod

    from module.config.deep import deep_iter
    from pywebio.output import put_column, put_html, put_row

    task = 'ProalasSmartDispatch'
    group_name = 'ProalasSmartDispatch'
    group_args = {arg[0]: arg_dict for arg, arg_dict in deep_iter(task_args.get(group_name, {}), depth=1)}
    config_data = config.data if hasattr(config, 'data') else config

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-sd-pref-card {{
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
  padding: 8px 10px; gap: 0 !important;
}}
.pa-sd-pref-card .pa-cfg-row {{ border-bottom: none; padding: 4px 0 !important; }}
.pa-sd-pref-row {{ gap: 10px !important; margin-top: 0 !important; }}
.pa-sd-pref-title {{
  font-size: 11px; font-weight: 600; color: #64748b; margin: 0 0 2px;
  letter-spacing: .03em;
}}
</style>
<div class="pa-proalas-hero">
  <h4>智能资源调度</h4>
  <p>按资源偏好（钻石 / 物资）调整后续自动化策略。下方偏好<strong>二选一</strong>，开启「物资」将自动关闭「钻石」。</p>
</div>
        """
    )

    card_rows = []
    master_arg = group_args.get('EnableSmartDispatch', {})
    if master_arg:
        row = _pa_config_row(
            task, group_name, 'EnableSmartDispatch', master_arg, config_data, scope_prefix='sd',
        )
        if row is not None:
            card_rows.append(row)

    if card_rows:
        put_column(card_rows).style('pa-proalas-card')

    pref_cols = []
    pref_meta = {
        'PreferRmb': ('钻石偏好', '#38bdf8'),
        'PreferMoney': ('物资偏好', '#eab308'),
    }
    for arg_name in ('PreferRmb', 'PreferMoney'):
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        title, dot_color = pref_meta.get(arg_name, ('', '#94a3b8'))
        row = _pa_config_row(
            task, group_name, arg_name, arg_dict, config_data, scope_prefix='sd',
        )
        if row is None:
            continue
        pref_cols.append(
            put_column([
                put_html(
                    f'<p class="pa-sd-pref-title">'
                    f'<span style="color:{dot_color}">●</span> {title}</p>'
                ),
                row,
            ]).style('pa-sd-pref-card')
        )

    if pref_cols:
        from pywebio.output import put_row
        put_row(pref_cols, size='1fr 1fr').style('pa-sd-pref-row')

    prefer_rmb_name = f'{task}_{group_name}_PreferRmb'
    prefer_money_name = f'{task}_{group_name}_PreferMoney'
    put_html(
        f"""
<script>
(function() {{
  function findSwitch(name) {{
    return document.querySelector('input[name="' + name + '"]')
      || document.querySelector('[data-pin="' + name + '"] input');
  }}
  function bindExclusive() {{
    var rmb = findSwitch({json_mod.dumps(prefer_rmb_name)});
    var money = findSwitch({json_mod.dumps(prefer_money_name)});
    if (!rmb || !money) return setTimeout(bindExclusive, 200);
    function sync(from, to) {{
      from.addEventListener('change', function() {{
        if (from.checked) {{
          to.checked = false;
          to.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }} else if (!to.checked) {{
          from.checked = true;
        }}
      }});
    }}
    sync(rmb, money);
    sync(money, rmb);
    if (rmb.checked && money.checked) money.checked = false;
    if (!rmb.checked && !money.checked) rmb.checked = true;
  }}
  bindExclusive();
}})();
</script>
        """
    )


def _afc_field_label(group_name: str, arg_name: str, *, fallback: str) -> str:
    """从 i18n name 取「·」后短标签，避免 .short 缺失时显示键名。"""
    from module.webui.lang import t

    full = t(f'{group_name}.{arg_name}.name')
    if full.startswith(f'{group_name}.') or full.startswith('ProalasAutoFleetChange.'):
        return fallback
    if '·' in full:
        return full.split('·', 1)[1].strip()
    return full


_AFC_TEAM_COLORS = {
    1: '#38bdf8',
    2: '#818cf8',
    3: '#34d399',
    4: '#fbbf24',
    5: '#fb7185',
    6: '#a78bfa',
}


def _afc_build_team_card(
    team_id: int,
    task: str,
    group_name: str,
    group_args: dict,
    config_data: dict,
    config=None,
):
    """单队卡片：预览 HTML + 职能标签（Pro+ 可改类型下拉）。"""
    from pywebio.output import put_column, put_html, put_row

    from module.proalas.fleet_summary import format_team_fleet_html, format_team_fleet_stats_html
    from module.proalas.fleet_team_roles import (
        resolve_team_role,
        role_label_zh,
        team_roles_allow_config_override,
    )

    fleet_html = format_team_fleet_html(config_data, team_id)
    stats_html = format_team_fleet_stats_html(config_data, team_id)
    dot_color = _AFC_TEAM_COLORS.get(team_id, '#94a3b8')
    arg = f'Team{team_id}Type'
    type_arg = group_args.get(arg, {})
    team_role = resolve_team_role(config, team_id) if config is not None else type_arg.get('value', 'push')
    role_text = role_label_zh(team_role)
    allow_override = config is not None and team_roles_allow_config_override(config)

    parts = [
        put_html(
            f'<header class="pa-afc-card-head">'
            f'<h4 class="pa-afc-card-title">'
            f'<span class="pa-afc-dot" style="background:{dot_color}"></span>第 {team_id} 队</h4>'
            f'{stats_html}'
            f'</header>'
            f'<div class="pa-afc-fleet-inner">{fleet_html}</div>'
        ),
    ]
    if allow_override and type_arg and type_arg.get('display') != 'hide':
        widget = _put_task_widget(
            task, group_name, arg, type_arg, config_data,
            compact=True, hide_title=True,
        )
        if widget is not None:
            parts.append(
                put_row([
                    put_html('<span class="pa-afc-type-label">队伍类型</span>'),
                    widget,
                ], size='auto 1fr').style('pa-afc-card-foot pa-afc-card-foot--type')
            )
    else:
        parts.append(
            put_html(
                f'<div class="pa-afc-card-foot pa-afc-card-foot--type">'
                f'<span class="pa-afc-type-label">职能</span>'
                f'<span class="pa-afc-role-badge pa-afc-role-badge--{team_role}">{role_text}</span>'
                f'</div>'
            )
        )
    return put_column(parts, size=' '.join(['auto'] * len(parts))).style(f'pa-afc-card pa-afc-team-{team_id}')


def _afc_build_event_card(
    event_id: int,
    task: str,
    group_name: str,
    group_args: dict,
    config_data: dict,
):
    """活动配队卡片：真实 pin 开关。"""
    from pywebio.output import put_column, put_html, put_row

    from module.config.deep import deep_get

    arg = f'EventTeam{event_id}Enable'
    enable_arg = group_args.get(arg, {})
    enabled = bool(deep_get(config_data, [task, group_name, arg], enable_arg.get('value', False)))
    status_cls = 'pa-afc-event-status--on' if enabled else 'pa-afc-event-status--off'
    status_text = '已启用' if enabled else '未启用'

    parts = [
        put_html(
            f'<header class="pa-afc-card-head">'
            f'<h4 class="pa-afc-card-title">'
            f'<span class="pa-afc-dot" style="background:#f472b6"></span>活动配队 {event_id}</h4>'
            f'<span class="pa-afc-event-status {status_cls}">{status_text}</span>'
            f'</header>'
            f'<p class="pa-afc-event-hint">固定编队（写死），仅控制是否参与自动换队。</p>'
        ),
    ]
    if enable_arg and enable_arg.get('display') != 'hide':
        widget = _put_task_widget(
            task, group_name, arg, enable_arg, config_data,
            compact=True, hide_title=True,
        )
        if widget is not None:
            parts.append(
                put_row([widget]).style('pa-afc-card-foot pa-afc-card-foot--event pa-afc-event-pin')
            )
    return put_column(parts, size=' '.join(['auto'] * len(parts))).style('pa-afc-card pa-afc-event-card')


def render_auto_fleet_change_panel(config, task_args: dict) -> None:
    """自动更换队伍：六队小卡片 + 活动配队。"""
    from module.config.deep import deep_iter
    from pywebio.output import put_column, put_html, put_row

    task = 'ProalasAutoFleetChange'
    group_name = 'ProalasAutoFleetChange'
    group_args = {arg[0]: arg_dict for arg, arg_dict in deep_iter(task_args.get(group_name, {}), depth=1)}
    config_data = config.data if hasattr(config, 'data') else config

    interval_row = _pa_config_row(
        task, group_name, 'RunIntervalDays',
        group_args.get('RunIntervalDays', {}),
        config_data,
        scope_prefix='afc',
    )
    faction_row = _pa_config_row(
        task, group_name, 'LevelTeamFaction',
        group_args.get('LevelTeamFaction', {}),
        config_data,
        scope_prefix='afc',
    )

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-afc-settings-wrap {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-afc-settings-title {{
  margin: 0 0 8px; font-size: 13px; font-weight: 700; color: #1e293b;
}}
.pa-afc-board {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-afc-wrap {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: start;
}}
scope.pa-afc-wrap {{
  display: grid !important; grid-template-columns: 1fr 1fr !important;
  gap: 12px !important; align-items: start !important;
}}
.pa-afc-col {{ display: flex; flex-direction: column; gap: 10px; }}
scope.pa-afc-col {{
  display: flex !important; flex-direction: column !important; gap: 10px !important;
}}
scope.pa-afc-col > * {{ margin: 0 !important; }}
scope.pa-afc-col > div[style*="display: grid"] {{
  grid-template-rows: auto !important; align-content: start !important;
}}
scope.pa-afc-card > div[style*="display: grid"] {{
  grid-template-rows: auto !important; align-content: start !important;
}}
scope.pa-afc-board > div[style*="display: grid"] {{
  grid-template-rows: auto !important; align-content: start !important;
}}
scope.pa-afc-card [style*="--arg-title--"],
.pa-afc-card-foot--type [style*="--arg-title--"] {{
  display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important;
  overflow: hidden !important;
}}
scope.pa-afc-card [id^="pywebio-scope-arg_container-"],
.pa-afc-card-foot--type [id^="pywebio-scope-arg_container-"] {{
  margin: 0 !important; padding: 0 !important; display: block !important;
}}
scope.pa-afc-card-foot--type,
.pa-afc-card-foot--type {{
  display: flex !important; align-items: center !important;
  margin: 8px 0 0 !important; padding: 8px 0 0 !important;
  border-top: 1px solid #f1f5f9 !important; min-height: 0 !important;
}}
scope.pa-afc-card-foot--type > div[style*="display: grid"],
.pa-afc-card-foot--type > div[style*="display: grid"] {{
  width: 100% !important; grid-template-columns: auto 1fr !important;
  align-items: center !important; min-height: 0 !important;
}}
.pa-afc-card {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
scope.pa-afc-card {{
  background: #fff !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important;
  padding: 10px 12px !important; margin: 0 !important;
  box-shadow: 0 1px 3px rgba(15,23,42,.05) !important;
  gap: 0 !important;
}}
scope.pa-afc-card > * {{ margin: 0 !important; }}
scope.pa-afc-board {{
  background: #fff !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important;
  padding: 12px 14px !important; margin: 0 0 12px !important;
  box-shadow: 0 1px 3px rgba(15,23,42,.05) !important;
  gap: 0 !important;
}}
scope.pa-afc-settings-wrap {{
  background: #fff !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important;
  padding: 10px 12px !important; margin: 0 0 12px !important;
  box-shadow: 0 1px 3px rgba(15,23,42,.05) !important;
  gap: 0 !important;
}}
.pa-afc-card-head {{
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  gap: 6px; margin: 0 0 6px;
}}
.pa-afc-card-title {{
  margin: 0; font-size: 13px; font-weight: 600; color: #1e293b;
  display: flex; align-items: center; gap: 6px;
}}
.pa-afc-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.pa-afc-stats {{ font-size: 11px; color: #64748b; font-variant-numeric: tabular-nums; }}
.pa-afc-fleet-inner {{ margin: 0; }}
.pa-afc-formation {{ display: flex; flex-direction: column; gap: 6px; }}
.pa-afc-row-head {{ display: flex; align-items: center; gap: 6px; margin: 0 0 2px; }}
.pa-afc-row-tag {{
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  padding: 1px 6px; border-radius: 4px;
}}
.pa-afc-tag-vanguard {{ background: #e0f2fe; color: #0369a1; }}
.pa-afc-tag-main {{ background: #fef3c7; color: #b45309; }}
.pa-afc-row-sub {{ font-size: 10px; color: #94a3b8; }}
.pa-afc-ships {{ display: flex; flex-direction: column; gap: 2px; }}
.pa-afc-ship {{
  display: grid; grid-template-columns: 28px 1fr auto; align-items: center; gap: 6px;
  padding: 2px 6px; border-radius: 6px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  font-size: 12px; line-height: 1.25; color: #334155;
}}
.pa-afc-ship-empty {{ opacity: .65; border-style: dashed; background: #fff; }}
.pa-afc-ship-slot {{ font-size: 10px; font-weight: 600; color: #94a3b8; text-align: center; }}
.pa-afc-ship-name {{ word-break: break-word; font-weight: 500; }}
.pa-afc-ship-pwr {{
  font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
  color: #b45309; white-space: nowrap;
}}
.pa-afc-empty-box {{
  text-align: center; padding: 10px 6px;
  border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc;
}}
.pa-afc-empty-icon {{ font-size: 20px; opacity: .5; margin-bottom: 4px; }}
.pa-afc-empty {{ margin: 0 0 2px; font-size: 12px; color: #475569; }}
.pa-afc-empty-hint {{ margin: 0; font-size: 11px; color: #94a3b8; line-height: 1.45; }}
.pa-afc-card-foot {{
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin: 8px 0 0; padding: 8px 0 0; border-top: 1px solid #f1f5f9;
}}
.pa-afc-card-foot--type {{
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}}
.pa-afc-type-label {{
  font-size: 12px; font-weight: 600; color: #64748b; white-space: nowrap;
}}
.pa-afc-role-badge {{
  font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
  border: 1px solid #e2e8f0; background: #f8fafc; color: #334155;
}}
.pa-afc-role-badge--push {{ background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }}
.pa-afc-role-badge--level {{ background: #ecfdf5; color: #047857; border-color: #a7f3d0; }}
.pa-afc-role-badge--low_cost {{ background: #fff7ed; color: #c2410c; border-color: #fed7aa; }}
.pa-afc-card-foot--type [id^="pywebio-scope-arg_container-select-"] {{
  margin: 0 !important; flex: 1 1 auto; max-width: 148px;
}}
.pa-afc-card-foot--type select.form-control {{
  font-size: 12px; padding: 4px 8px; min-height: 30px; border-radius: 8px;
}}
.pa-afc-event-pin [id^="pywebio-scope-arg_container-checkbox-"] {{
  margin: 0 !important;
}}
.pa-afc-event-pin .custom-checkbox {{ margin: 0; }}
.pa-afc-section-title {{
  margin: 12px 0 10px; font-size: 13px; font-weight: 700; color: #1e293b;
}}
.pa-afc-event-wrap {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
}}
scope.pa-afc-event-wrap {{
  display: grid !important; grid-template-columns: 1fr 1fr !important; gap: 10px !important;
}}
.pa-afc-event-hint {{
  margin: 0 0 6px; font-size: 11px; color: #94a3b8; line-height: 1.45;
}}
.pa-afc-event-status {{
  font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
}}
.pa-afc-event-status--on {{ background: #dcfce7; color: #15803d; }}
.pa-afc-event-status--off {{ background: #f1f5f9; color: #64748b; }}
@media (max-width: 900px) {{
  .pa-afc-wrap, .pa-afc-event-wrap {{ grid-template-columns: 1fr; }}
}}
</style>
<div class="pa-proalas-hero">
  <h4>舰队编成 · 换队策略</h4>
  <p>六队编队预览来自 <strong>编队采集</strong>。职能固定：<strong>1–2 推图、3–4 练级、5–6 低耗</strong>（仅练级队执行换船，可指定阵营筛选）。Pro+ 可改队伍类型。活动配队为固定编队，仅开关。</p>
</div>
        """
    )

    interval_parts = [put_html('<h4 class="pa-afc-settings-title">练级换船</h4>')]
    if interval_row is not None:
        interval_parts.append(interval_row)
    if faction_row is not None:
        interval_parts.append(faction_row)
    put_column(
        interval_parts,
        size=' '.join(['auto'] * len(interval_parts)),
    ).style('pa-afc-settings-wrap')

    left_cards = [
        _afc_build_team_card(team_id, task, group_name, group_args, config_data, config)
        for team_id in range(1, 4)
    ]
    right_cards = [
        _afc_build_team_card(team_id, task, group_name, group_args, config_data, config)
        for team_id in range(4, 7)
    ]
    event_cards = [
        _afc_build_event_card(event_id, task, group_name, group_args, config_data)
        for event_id in range(1, 3)
    ]

    board_parts = [
        put_row([
            put_column(
                left_cards,
                size=' '.join(['auto'] * len(left_cards)),
            ).style('pa-afc-col pa-afc-col-left'),
            put_column(
                right_cards,
                size=' '.join(['auto'] * len(right_cards)),
            ).style('pa-afc-col pa-afc-col-right'),
        ], size='1fr 1fr').style('pa-afc-wrap'),
        put_html('<h3 class="pa-afc-section-title">活动配队</h3>'),
        put_row(event_cards, size='1fr 1fr').style('pa-afc-event-wrap'),
    ]
    put_column(
        board_parts,
        size=' '.join(['auto'] * len(board_parts)),
    ).style('pa-afc-board')


def render_account_plan_panel(config, task_args: dict, device_id: str = '') -> None:
    """账户管理：套餐类型 / 到期时间 / 续费 + QQ 绑定（每月限改一次）。"""
    from html import escape

    from module.config.deep import deep_get
    from module.proalas.qq_binding import (
        can_change_binding,
        get_device_binding,
    )
    from pywebio.output import put_buttons, put_html, toast
    from pywebio.pin import pin, put_input

    _ = task_args
    config_data = config.data if hasattr(config, 'data') else config
    cfg_path = ['ProalasAccount', 'ProalasAccount']
    device_id = device_id or str(getattr(config, 'config_name', '') or '')

    plan = str(deep_get(config_data, cfg_path + ['PlanType'], 'normal') or 'normal')
    plan_labels = {'normal': 'Normal', 'pro': 'Pro', 'pro_plus': 'Pro+'}
    plan_text = plan_labels.get(plan, 'Normal')
    plan_css = {
        'normal': 'pa-acc-badge-normal',
        'pro': 'pa-acc-badge-pro',
        'pro_plus': 'pa-acc-badge-proplus',
    }.get(plan, 'pa-acc-badge-normal')

    expire_raw = deep_get(config_data, cfg_path + ['ExpireAt'], '')
    if hasattr(expire_raw, 'strftime'):
        expire_text = expire_raw.strftime('%Y-%m-%d %H:%M:%S')
    else:
        expire_text = str(expire_raw or '—')

    renewal_url = str(deep_get(config_data, cfg_path + ['RenewalUrl'], '') or '').strip()
    if renewal_url:
        renew_html = (
            f'<a class="pa-acc-renew-btn" href="{escape(renewal_url)}" '
            f'target="_blank" rel="noopener">前往续费</a>'
        )
    else:
        renew_html = '<span class="pa-acc-renew-empty">续费入口暂未配置</span>'

    bind_row = get_device_binding(device_id) if device_id else {}
    bound_qq = str(bind_row.get('qq_id') or '').strip()
    if device_id and bound_qq:
        from module.proalas.qq_binding import sync_binding_plan_from_config

        sync_binding_plan_from_config(device_id, plan)
    bound_qq_text = bound_qq if bound_qq else '未绑定'
    can_change, next_at = can_change_binding(device_id) if device_id else (True, '')
    if bound_qq and next_at:
        change_hint = f'下次可更改：{next_at}'
    elif bound_qq:
        change_hint = '每月仅可更改一次绑定'
    else:
        change_hint = '绑定后可通过 QQ 发送 stop-3h 等指令（Router 接入后生效）'

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-acc-plan-card {{ padding: 16px 18px !important; }}
.pa-acc-plan-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px 24px;
  margin-bottom: 14px;
}}
@media (max-width: 640px) {{ .pa-acc-plan-grid {{ grid-template-columns: 1fr; }} }}
.pa-acc-plan-label {{
  display: block; font-size: 12px; font-weight: 600; color: #64748b;
  letter-spacing: .04em; margin-bottom: 8px;
}}
.pa-acc-plan-badge {{
  display: inline-block; font-size: 26px; font-weight: 800; line-height: 1.2;
  padding: 4px 0;
}}
.pa-acc-badge-normal {{ color: #475569; }}
.pa-acc-badge-pro {{ color: #4f46e5; }}
.pa-acc-badge-proplus {{ color: #7c3aed; }}
.pa-acc-plan-expire {{
  display: block; font-size: 20px; font-weight: 700; color: #0f172a;
  font-variant-numeric: tabular-nums; line-height: 1.35;
}}
.pa-acc-renew-row {{
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding-top: 12px; border-top: 1px solid #f1f5f9;
}}
.pa-acc-renew-label {{ font-size: 13px; font-weight: 600; color: #334155; }}
.pa-acc-renew-btn {{
  display: inline-block; padding: 8px 18px; border-radius: 8px;
  background: #4f46e5; border: 1px solid #4338ca;
  color: #fff !important; text-decoration: none; font-size: 13px; font-weight: 600;
}}
.pa-acc-renew-btn:hover {{ background: #4338ca; }}
.pa-acc-renew-empty {{ font-size: 13px; color: #94a3b8; }}
.pa-acc-qq-card {{ padding: 14px 18px !important; }}
.pa-acc-qq-meta {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px 20px;
  margin-bottom: 12px; font-size: 14px;
}}
@media (max-width: 640px) {{ .pa-acc-qq-meta {{ grid-template-columns: 1fr; }} }}
.pa-acc-qq-meta dt {{
  font-size: 12px; font-weight: 600; color: #64748b; margin: 0 0 4px;
}}
.pa-acc-qq-meta dd {{
  margin: 0; font-size: 15px; font-weight: 600; color: #1e293b;
}}
.pa-acc-qq-form {{
  margin: 8px 0 10px; padding: 12px 14px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
}}
.pa-acc-qq-form label {{ font-size: 13px; font-weight: 600; color: #334155; }}
.pa-acc-qq-form input {{
  border-radius: 8px !important; border-color: #cbd5e1 !important;
  font-size: 14px !important; padding: 8px 12px !important;
}}
.pa-acc-qq-actions {{ margin: 10px 0 6px; }}
.pa-acc-qq-foot {{
  font-size: 12px; color: #94a3b8; margin: 8px 0 0; line-height: 1.5;
}}
.pa-acc-qq-warn {{
  font-size: 13px; color: #b45309; background: #fffbeb;
  border: 1px solid #fde68a; border-radius: 8px; padding: 8px 12px; margin: 8px 0;
}}
.pa-tt-sub {{
  font-size: 14px; font-weight: 600; color: #334155;
  margin: 0 0 6px;
}}
.pa-tt-sub-hint {{
  font-size: 12px; color: #94a3b8; margin: 0; line-height: 1.5;
}}
</style>
<div class="pa-proalas-hero">
  <h4>账户管理</h4>
  <p>套餐由付费状态决定，此处只读展示；到期后请续费。QQ 绑定用于远程指令（每月限改一次）。</p>
</div>
<div class="pa-proalas-card pa-acc-plan-card">
  <div class="pa-acc-plan-grid">
    <div>
      <span class="pa-acc-plan-label">当前套餐类型</span>
      <span class="pa-acc-plan-badge {plan_css}">{escape(plan_text)}</span>
    </div>
    <div>
      <span class="pa-acc-plan-label">到期时间</span>
      <span class="pa-acc-plan-expire">{escape(expire_text)}</span>
    </div>
  </div>
  <div class="pa-acc-renew-row">
    <span class="pa-acc-renew-label">续费管理</span>
    {renew_html}
  </div>
</div>
<div class="pa-proalas-card pa-acc-qq-card">
  <p class="pa-tt-sub" style="margin-top:0">QQ 远程绑定</p>
  <p class="pa-tt-sub-hint" style="margin-bottom:12px">v1：一个 QQ 仅绑定本设备；每月最多更改一次。</p>
  <dl class="pa-acc-qq-meta">
    <div><dt>已绑定 QQ</dt><dd>{escape(bound_qq_text)}</dd></div>
    <div><dt>更改限制</dt><dd>{escape(change_hint)}</dd></div>
  </dl>
  <div class="pa-acc-qq-form">
        """
    )

    put_input(
        'pa_qq_bind_input',
        label='QQ 号',
        value=bound_qq,
        placeholder='5～12 位数字',
    )

    put_html('</div>')

    def _on_bind_qq():
        from module.proalas.qq_binding import bind_qq, sync_binding_plan_from_config

        qq_val = str(pin.pa_qq_bind_input or '').strip()
        ok, msg = bind_qq(device_id, qq_val)
        if ok:
            sync_binding_plan_from_config(device_id, plan)
        toast(msg, color='success' if ok else 'error')

    def _on_unbind_qq():
        from module.proalas.qq_binding import unbind_qq

        ok, msg = unbind_qq(device_id)
        toast(msg, color='success' if ok else 'error')

    if can_change:
        labels = ['保存绑定']
        actions = ['bind']
        if bound_qq:
            labels.append('解除绑定')
            actions.append('unbind')

        def _qq_btn_click(action):
            if action == 'bind':
                _on_bind_qq()
            elif action == 'unbind':
                _on_unbind_qq()

        put_html('<div class="pa-acc-qq-actions">')
        put_buttons(
            labels,
            onclick=[lambda a=act: _qq_btn_click(a) for act in actions],
        )
        put_html('</div>')
    else:
        put_html(f'<p class="pa-acc-qq-warn">本月已更改过绑定，请到期后再试。</p>')

    put_html(
        f'<p class="pa-acc-qq-foot">设备 ID：<strong>{escape(device_id or "—")}</strong>'
        f' · 写入 <code>mumucontrol/runtime/qq_bindings.json</code>（QQ Router 接入后生效）</p>'
        '</div>'
    )


def _pa_scheduler_rows(
    task: str,
    task_args: dict,
    config_data: dict,
    *,
    scope_prefix: str,
    fields: tuple[str, ...] = ('Enable', 'NextRun', 'SuccessInterval', 'ServerUpdate'),
):
    """子任务 Scheduler 行（合并页强制展示 Enable）。"""
    from module.config.deep import deep_iter
    from pywebio.output import put_column

    sched_args = {
        arg[0]: arg_dict
        for arg, arg_dict in deep_iter(task_args.get('Scheduler', {}), depth=1)
    }
    rows = []
    for field in fields:
        arg_dict = sched_args.get(field, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        ad = dict(arg_dict)
        if field == 'Enable' and ad.get('display') == 'hide':
            ad.pop('display', None)
        row = _pa_config_row(task, 'Scheduler', field, ad, config_data, scope_prefix=scope_prefix)
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    return put_column(rows).style('pa-proalas-card')


def _pa_task_option_rows(
    task: str,
    task_args: dict,
    config_data: dict,
    *,
    scope_prefix: str,
    field_order: tuple[str, ...],
):
    from module.config.deep import deep_iter
    from pywebio.output import put_column

    group_args = {
        arg[0]: arg_dict
        for arg, arg_dict in deep_iter(task_args.get(task, {}), depth=1)
    }
    rows = []
    for arg_name in field_order:
        arg_dict = group_args.get(arg_name, {})
        if not arg_dict or arg_dict.get('type') == 'storage':
            continue
        row = _pa_config_row(task, task, arg_name, arg_dict, config_data, scope_prefix=scope_prefix)
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    return put_column(rows).style('pa-proalas-card')


def render_timer_plan_panel(
    device_id: str,
    config,
    task_args: dict,
    *,
    activity_args: dict | None = None,
    gacha_args: dict | None = None,
    fill_args: dict | None = None,
) -> None:
    """定时计划：TimeTable 快照 + 调度排除 + 活动同步 + UP / 科研补齐说明。"""
    from html import escape

    from module.proalas.collection_fill_policy import research_next_due_hint
    from module.proalas.time_table import read_device_timetable, timetable_path
    from pywebio.output import put_html

    activity_args = activity_args or {}
    gacha_args = gacha_args or {}
    fill_args = fill_args or {}
    config_data = config.data if hasattr(config, 'data') else config

    snap = read_device_timetable(device_id)
    path = timetable_path()
    if snap:
        status = '需要运行' if snap.get('needRunning') else '可关闭 MuMu'
        status_cls = 'pa-tt-on' if snap.get('needRunning') else 'pa-tt-off'
        tt_body = f"""
        <ul class="pa-tt-list">
          <li><span>运行状态</span><strong class="{status_cls}">{escape(status)}</strong></li>
          <li><span>最早任务</span><strong>{escape(str(snap.get('earliestCommand') or '—'))}</strong></li>
          <li><span>最早时间</span><strong>{escape(str(snap.get('earliestNextRun') or '—'))}</strong></li>
          <li><span>待运行</span><strong>{escape(', '.join(snap.get('pendingCommands') or []) or '无')}</strong></li>
          <li><span>已启用任务数</span><strong>{snap.get('enabledTaskCount', 0)}</strong></li>
          <li><span>更新时间</span><strong>{escape(str(snap.get('updatedAt') or '—'))}</strong></li>
        </ul>
        """
    else:
        tt_body = (
            '<p class="pa-tt-empty">尚无 TimeTable 记录。请确认本机已运行 '
            '<code>python -m mumucontrol</code>（HostAgent 约每 5 分钟刷新）。</p>'
        )

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-tt-wrap {{ margin: 0 0 4px; }}
.pa-tt-list {{ list-style: none; padding: 0; margin: 0; font-size: 13px; }}
.pa-tt-list li {{
  display: flex; justify-content: space-between; gap: 12px;
  padding: 8px 0; border-bottom: 1px solid #f1f5f9;
}}
.pa-tt-list li:last-child {{ border-bottom: none; }}
.pa-tt-list li span {{ color: #64748b; }}
.pa-tt-on {{ color: #16a34a; font-weight: 600; }}
.pa-tt-off {{ color: #64748b; font-weight: 600; }}
.pa-tt-foot {{ font-size: 11px; color: #94a3b8; margin: 8px 0 0; }}
.pa-tt-empty {{ font-size: 12px; color: #64748b; margin: 0; line-height: 1.55; }}
.pa-tt-sub {{
  font-size: 13px; font-weight: 600; color: #334155;
  margin: 12px 0 6px; padding-top: 2px;
}}
.pa-tt-sub-hint {{
  font-size: 11px; color: #94a3b8; margin: 0 0 8px; line-height: 1.5;
}}
</style>
<div class="pa-proalas-hero">
  <h4>定时计划</h4>
  <p>汇总本机已启用任务的最早 <code>NextRun</code>，供 HostAgent 决定 MuMu / Alas 启停。
  请先启用下方<strong>定时计划主开关</strong>；活动同步、蓝区 UP 检测、到期科研扫描均随主任务运行。</p>
</div>
<div class="pa-proalas-card pa-tt-wrap">
  <p class="pa-tt-sub">TimeTable 快照</p>
  <p class="pa-tt-sub-hint">由 HostAgent 写入 <code>{escape(path)}</code>；
  「可关闭 MuMu」表示当前无到期任务。</p>
  {tt_body}
  <p class="pa-tt-foot">设备：{escape(device_id or '—')}</p>
</div>
        """
    )

    put_html(
        f'<p class="pa-tt-sub">{escape(_pa_i18n_text("ProalasTimerPlan", "_info", "name", fallback="定时计划"))}</p>'
        f'<p class="pa-tt-sub-hint">'
        f'下方<strong>主开关</strong>启用后，Alas 队列仅出现「定时计划」；'
        f'活动同步与补齐检测按节奏随主任务运行。'
        f'</p>'
    )
    sched_master = _pa_scheduler_rows(
        'ProalasTimerPlan', task_args, config_data, scope_prefix='tp_master',
        fields=('Enable', 'NextRun', 'SuccessInterval', 'ServerUpdate'),
    )
    if sched_master is not None:
        sched_master

    exclude_card = _pa_task_option_rows(
        'ProalasTimerPlan',
        task_args,
        config_data,
        scope_prefix='tp',
        field_order=('ExtraExclude',),
    )
    if exclude_card is not None:
        put_html('<p class="pa-tt-sub">调度统计排除</p>')
        put_html(
            '<p class="pa-tt-sub-hint">'
            '逗号分隔的 Scheduler.Command，不参与「最早 NextRun」统计（HostAgent 刷新 TimeTable 时读取）。'
            '</p>'
        )
        exclude_card

    put_html(
        f'<p class="pa-tt-sub">{escape(_pa_i18n_text("ProalasActivitySync", "_info", "name", fallback="活动同步"))}</p>'
        f'<p class="pa-tt-sub-hint">{escape(_pa_i18n_text("ProalasActivitySync", "_info", "help", fallback=""))}'
        f' · 随上方「定时计划」主开关运行</p>'
    )
    opt_act = _pa_task_option_rows(
        'ProalasActivitySync',
        activity_args,
        config_data,
        scope_prefix='tp_as',
        field_order=(
            'SyncGatewayEnable',
            'SyncGatewayUrl',
            'SyncGatewayToken',
            'PullPlanSchedule',
            'AllowManifestFallback',
        ),
    )
    if opt_act is not None:
        opt_act

    put_html(
        f'<p class="pa-tt-sub">{escape(_pa_i18n_text("ProalasGachaCheck", "_info", "name", fallback="UP 抽卡检测"))}</p>'
        f'<p class="pa-tt-sub-hint">{escape(_pa_i18n_text("ProalasGachaCheck", "_info", "help", fallback=""))}'
        f' · <strong>仅蓝区活动日</strong>随定时计划运行；非活动日跳过</p>'
    )
    opt_gacha = _pa_task_option_rows(
        'ProalasGachaCheck',
        gacha_args,
        config_data,
        scope_prefix='tp_gc',
        field_order=('BootstrapNullTemplate',),
    )
    if opt_gacha is not None:
        opt_gacha

    research_due = research_next_due_hint(config_data)
    put_html(
        f'<p class="pa-tt-sub">自动补齐图鉴（检测节奏）</p>'
        f'<p class="pa-tt-sub-hint">'
        f'总开关与三个子开关控制是否参与；开关也可在「自动补齐图鉴」页调整。<br>'
        f'· <strong>建造补齐</strong>：UP 检测跟蓝区；自动建造另需「自动抽卡补齐」<br>'
        f'· <strong>科研补齐</strong>：开发船坞扫描（默认每 7 天到期一次）'
        f' · 下次/状态：{escape(research_due)}<br>'
        f'· <strong>打捞补齐</strong>：预定按定时间隔检测（逻辑待接）'
        f'</p>'
    )
    opt_fill = _pa_task_option_rows(
        'ProalasCollectionFill',
        fill_args,
        config_data,
        scope_prefix='tp_cf',
        field_order=(
            'Enable',
            'BuildEnable',
            'FarmEnable',
            'ResearchEnable',
            'ResearchIntervalDays',
            'AutoGachaEnable',
        ),
    )
    if opt_fill is not None:
        opt_fill


def render_plan_calendar_panel(device_id: str, *, enable_ai: bool) -> None:
    """计划表：四色象限日历 + 接口说明。"""
    from datetime import date

    from module.proalas.plan_schedule_api import export_plan_api_spec, get_plan_month_view

    today = date.today()
    view = get_plan_month_view(device_id, today.year, today.month)
    spec = export_plan_api_spec()
    ai_tip = '已开启（接口就绪，对话功能待接入）' if enable_ai else '未开启（可在下方 EnableAi 打开；功能待 AI 对接）'

    quad_colors = {
        'yellow': '#fbbf24',
        'red': '#f87171',
        'green': '#4ade80',
        'blue': '#60a5fa',
    }

    weeks_html = []
    for week in view.get('weeks') or []:
        cells = []
        for cell in week:
            if not cell.get('inMonth'):
                cells.append('<td class="pa-cal-pad"></td>')
                continue
            n = len(cell.get('entries') or [])
            badge = f'<span class="pa-cal-badge">{n}</span>' if n else ''
            cls = ' pa-cal-today' if cell.get('isToday') else ''
            quads = cell.get('quadrants') or {}
            quad_dots = []
            for key, color in quad_colors.items():
                if quads.get(key):
                    quad_dots.append(f'<span class="pa-cal-dot" style="background:{color}" title="{key}"></span>')
            dots_html = f'<div class="pa-cal-dots">{"".join(quad_dots)}</div>' if quad_dots else ''
            cells.append(
                f'<td class="pa-cal-day{cls}"><div class="pa-cal-num">{cell.get("day")}{badge}</div>{dots_html}</td>'
            )
        weeks_html.append(f'<tr>{"".join(cells)}</tr>')

    table = (
        '<table class="pa-cal-table"><thead><tr>'
        + ''.join(f'<th>{w}</th>' for w in view.get('weekdays') or [])
        + '</tr></thead><tbody>'
        + ''.join(weeks_html)
        + '</tbody></table>'
    )

    methods = ', '.join(m['name'] for m in spec.get('methods') or [])

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-cal-wrap {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-cal-head {{ margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #1e293b; }}
.pa-cal-intro {{ margin: 0 0 10px; font-size: 12px; color: #64748b; line-height: 1.55; }}
.pa-cal-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.pa-cal-table th, .pa-cal-table td {{ border: 1px solid #e2e8f0; text-align: center; padding: 6px 4px; color: #334155; }}
.pa-cal-day {{ min-height: 36px; vertical-align: top; }}
.pa-cal-today {{ background: #eef2ff; }}
.pa-cal-pad {{ background: #f8fafc; }}
.pa-cal-num {{ position: relative; }}
.pa-cal-badge {{
  display: inline-block; margin-left: 2px; padding: 0 4px; border-radius: 8px;
  background: #dbeafe; color: #1d4ed8; font-size: 10px;
}}
.pa-cal-dots {{ display: flex; justify-content: center; gap: 3px; margin-top: 4px; }}
.pa-cal-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
.pa-cal-legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 0 0 10px; font-size: 11px; color: #64748b; }}
.pa-cal-legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
.pa-cal-api {{
  margin-top: 10px; padding: 10px 12px; border-radius: 8px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  font-size: 11px; line-height: 1.55; font-family: ui-monospace, monospace; color: #475569;
}}
</style>
<div class="pa-cal-wrap">
  <h4 class="pa-cal-head">计划表 · {view.get('monthLabel')}</h4>
  <p class="pa-cal-intro">
    AI 功能：{ai_tip}。全局日历 <code>config/proalas/GlobalActivityCalendar.json</code>，设备计划 <code>{spec.get('storage')}</code>，本月条目 {view.get('entryCount', 0)} 条。
  </p>
  <div class="pa-cal-legend">
    <span><i class="pa-cal-dot" style="background:#fbbf24"></i>黄·日常</span>
    <span><i class="pa-cal-dot" style="background:#f87171"></i>红·主动</span>
    <span><i class="pa-cal-dot" style="background:#4ade80"></i>绿·人工</span>
    <span><i class="pa-cal-dot" style="background:#60a5fa"></i>蓝·活动</span>
  </div>
  {table}
  <div class="pa-cal-api">
    Python API（{spec.get('module')}）：<br/>
    {methods}
  </div>
</div>
        """
    )


def _cf_kv_row(label: str, value: str, *, value_cls: str = '') -> str:
    from html import escape

    cls = f' pa-cf-kv-val--{value_cls}' if value_cls else ''
    return (
        f'<div class="pa-cf-kv">'
        f'<span class="pa-cf-kv-key">{escape(label)}</span>'
        f'<span class="pa-cf-kv-val{cls}">{escape(value)}</span>'
        f'</div>'
    )


def _cf_gacha_settings_footer(config_data: dict, gacha: dict) -> str:
    from html import escape

    auto_label = str(gacha.get('autoLabel') or '—')
    last_run = str(gacha.get('autoLastRun') or '—')
    return (
        f'<footer class="pa-afc-card-foot pa-cf-settings">'
        f'<p class="pa-cf-settings-title">自动抽卡策略（硬限制）</p>'
        f'<div class="pa-cf-kv-list" style="margin:0">'
        f'{_cf_kv_row("执行状态", auto_label)}'
        f'{_cf_kv_row("上次运行", last_run, value_cls="muted")}'
        f'{_cf_kv_row("魔方下限", "500（固定）", value_cls="muted")}'
        f'{_cf_kv_row("每日上限", "20 发（固定）", value_cls="muted")}'
        f'</div>'
        f'<p class="pa-cf-card-hint" style="margin:8px 0 0">'
        f'开关见本页下方「自动抽卡补齐」；须关闭原版每日抽卡调度。'
        f'</p>'
        f'</footer>'
    )


def _cf_gacha_card_html(device_id: str, gacha: dict, config_data: dict) -> str:
    from html import escape

    status_cls = 'ok' if gacha.get('allOwned') is True else (
        'warn' if gacha.get('missing') or gacha.get('uncertain') else 'muted'
    )
    rows = [
        _cf_kv_row('检测状态', str(gacha.get('statusLabel') or '—'), value_cls=status_cls),
        _cf_kv_row('上次检测', str(gacha.get('lastCheckAt') or '—')),
        _cf_kv_row('UP 列表', '、'.join(gacha.get('upShips') or []) or '—'),
        _cf_kv_row('未拥有', str(gacha.get('missingText') or '—'), value_cls='warn' if gacha.get('missing') else ''),
    ]
    if gacha.get('uncertainText'):
        rows.append(_cf_kv_row('未确定', str(gacha['uncertainText']), value_cls='warn'))
    rows.append(_cf_kv_row('自动抽卡', str(gacha.get('autoLabel') or '—')))
    rows.append(_cf_kv_row('设备', str(device_id or '—'), value_cls='muted'))
    body = ''.join(rows)
    return (
        f'<article class="pa-afc-card pa-cf-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#818cf8"></span>'
        f'建造补齐 · UP 池</h4>'
        f'<span class="pa-cf-badge">自动抽卡</span>'
        f'</header>'
        f'<p class="pa-cf-card-hint">'
        f'检测来自 <code>ProalasData.GachaUp</code>；自动建造写 <code>GachaAuto</code>，'
        f'活动日由定时计划在检测后触发。'
        f'</p>'
        f'<div class="pa-cf-kv-list">{body}</div>'
        f'{_cf_gacha_settings_footer(config_data, gacha)}'
        f'</article>'
    )


def _cf_farm_card_html(farm: dict) -> str:
    active_cls = 'muted' if farm.get('activeText') in ('未开始', '—', '') else 'ok'
    rows = [
        _cf_kv_row('未拥有', str(farm.get('missingText') or '—')),
        _cf_kv_row('当前主线', str(farm.get('activeText') or '未开始'), value_cls=active_cls),
        _cf_kv_row('目标列表', '、'.join(farm.get('targets') or []) or '—'),
        _cf_kv_row('更新时间', str(farm.get('updatedAt') or '—'), value_cls='muted'),
    ]
    body = ''.join(rows)
    return (
        f'<article class="pa-afc-card pa-cf-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#34d399"></span>'
        f'打捞补齐 · 主线补齐</h4>'
        f'<span class="pa-cf-badge">状态展示</span>'
        f'</header>'
        f'<p class="pa-cf-card-hint">'
        f'目标来自 <code>CollectionFill.farm</code> 或日历 '
        f'<code>farm_ships</code>；执行状态待主线打捞任务回写。'
        f'</p>'
        f'<div class="pa-cf-kv-list">{body}</div>'
        f'</article>'
    )


def _cf_research_card_html(research: dict) -> str:
    incomplete_cls = 'ok' if research.get('incompleteCount') == 0 else (
        'warn' if research.get('incompleteCount') else 'muted'
    )
    position_cls = 'muted' if research.get('positionText') in ('未开始', '—', '') else 'ok'
    progress_cls = 'muted' if research.get('progressText') in ('未开始', '—', '') else 'ok'
    rows = [
        _cf_kv_row('未完成', str(research.get('incompleteText') or '—'), value_cls=incomplete_cls),
        _cf_kv_row('当前科研', str(research.get('positionText') or '—'), value_cls=position_cls),
        _cf_kv_row('当前进度', str(research.get('progressText') or '—'), value_cls=progress_cls),
        _cf_kv_row('扫描节奏', str(research.get('dueText') or '—'), value_cls='muted'),
        _cf_kv_row('上次扫描', str(research.get('updatedAt') or '—'), value_cls='muted'),
    ]
    body = ''.join(rows)
    return (
        f'<article class="pa-afc-card pa-cf-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#f59e0b"></span>'
        f'科研补齐 · 开发船坞</h4>'
        f'<span class="pa-cf-badge pa-cf-badge--soon">检测 · 周更</span>'
        f'</header>'
        f'<p class="pa-cf-card-hint">'
        f'数据来自 <code>CollectionFill.research</code>；'
        f'由定时计划按间隔扫描开发船坞（默认每周），结果写入未完成列表与 '
        f'<code>config/{{设备}}_research_incomplete.txt</code>。'
        f'</p>'
        f'<div class="pa-cf-kv-list">{body}</div>'
        f'</article>'
    )


def render_collection_fill_panel(device_id: str, config, task_args: dict) -> None:
    """自动补齐图鉴：两行看板（建造整行 + 打捞/科研并列）。"""
    from module.proalas.collection_fill_display import (
        build_farm_card_view,
        build_gacha_card_view,
        build_research_card_view,
    )
    from pywebio.output import put_html

    config_data = config.data if hasattr(config, 'data') else config
    gacha = build_gacha_card_view(config_data)
    farm = build_farm_card_view(config_data)
    research = build_research_card_view(config_data)

    gacha_html = _cf_gacha_card_html(device_id, gacha, config_data)
    farm_html = _cf_farm_card_html(farm)
    research_html = _cf_research_card_html(research)

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-cf-board {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
  display: flex; flex-direction: column; gap: 12px;
}}
.pa-cf-row {{ width: 100%; min-width: 0; }}
.pa-cf-row--bottom {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: stretch;
}}
.pa-cf-row--bottom > .pa-cf-card {{ min-width: 0; }}
.pa-afc-card {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-afc-card-head {{
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  gap: 6px; margin: 0 0 6px;
}}
.pa-afc-card-title {{
  margin: 0; font-size: 13px; font-weight: 600; color: #1e293b;
  display: flex; align-items: center; gap: 6px;
}}
.pa-afc-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.pa-afc-card-foot {{
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin: 10px 0 0; padding: 10px 0 0; border-top: 1px solid #f1f5f9;
}}
.pa-afc-check {{ width: 16px; height: 16px; margin: 0; }}
.pa-cf-card {{ margin: 0; height: 100%; box-sizing: border-box; }}
.pa-cf-card-hint {{
  margin: 0 0 10px; font-size: 11px; color: #94a3b8; line-height: 1.5;
}}
.pa-cf-card-hint code {{
  font-size: 10px; background: #f1f5f9; padding: 1px 4px; border-radius: 4px;
}}
.pa-cf-kv-list {{
  display: flex; flex-direction: column; gap: 0;
  border: 1px solid #f1f5f9; border-radius: 8px; overflow: hidden;
  background: #fafbfc;
}}
.pa-cf-kv {{
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; padding: 8px 10px;
  border-bottom: 1px solid #f1f5f9; font-size: 12px; line-height: 1.45;
}}
.pa-cf-kv:last-child {{ border-bottom: none; }}
.pa-cf-kv-key {{ flex: 0 0 auto; color: #64748b; min-width: 72px; }}
.pa-cf-kv-val {{
  flex: 1 1 auto; text-align: right; color: #1e293b; font-weight: 600;
  word-break: break-word;
}}
.pa-cf-kv-val--ok {{ color: #16a34a; }}
.pa-cf-kv-val--warn {{ color: #d97706; }}
.pa-cf-kv-val--muted {{ color: #64748b; font-weight: 500; }}
.pa-cf-badge {{
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  background: #f1f5f9; color: #64748b; font-size: 10px; font-weight: 700;
  white-space: nowrap;
}}
.pa-cf-badge--soon {{ background: rgba(99,102,241,.12); color: #4f46e5; }}
.pa-cf-settings {{ flex-direction: column; align-items: stretch; gap: 8px; }}
.pa-cf-settings-title {{
  margin: 0; font-size: 11px; font-weight: 600; color: #94a3b8;
}}
.pa-cf-settings-grid {{
  display: flex; flex-direction: column; gap: 8px; width: 100%;
}}
.pa-cf-setting {{
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  margin: 0; cursor: not-allowed;
}}
.pa-cf-setting-label {{ font-size: 12px; font-weight: 600; color: #64748b; }}
.pa-cf-setting-input {{
  width: 88px !important; min-height: 30px !important;
  padding: 2px 8px !important; font-size: 12px !important;
  text-align: right; background: #f8fafc !important; opacity: .85;
}}
@media (max-width: 640px) {{
  .pa-cf-row--bottom {{ grid-template-columns: 1fr; }}
}}
</style>
<div class="pa-proalas-hero">
  <h4>自动补齐图鉴</h4>
  <p>看板展示三线进度。检测节奏由<strong>定时计划</strong>编排：建造 UP 跟蓝区；科研默认每周到期扫描；打捞定时待接。真正补齐（科研任务 / 自动建造）另受下方子开关约束。</p>
</div>
<div class="pa-cf-board">
  <div class="pa-cf-row pa-cf-row--top">
    {gacha_html}
  </div>
  <div class="pa-cf-row pa-cf-row--bottom">
    {farm_html}
    {research_html}
  </div>
</div>
        """
    )


def _aip_command_rows_html(commands: list[dict[str, str]]) -> str:
    from html import escape

    if not commands:
        return (
            '<p class="pa-aip-empty">（无指令）</p>'
        )
    rows = []
    for row in commands:
        kind = escape(row.get('kind') or '指令')
        target = escape(row.get('target') or '—')
        value = escape(row.get('value') or '—')
        idx = escape(str(row.get('index') or ''))
        rows.append(
            f'<li class="pa-aip-cmd">'
            f'<span class="pa-aip-cmd-idx">{idx}</span>'
            f'<span class="pa-aip-cmd-kind">{kind}</span>'
            f'<span class="pa-aip-cmd-target">{target}</span>'
            f'<span class="pa-aip-cmd-arrow">→</span>'
            f'<span class="pa-aip-cmd-value">{value}</span>'
            f'</li>'
        )
    return f'<ol class="pa-aip-cmd-list">{"".join(rows)}</ol>'


def _render_ai_plan_board(plan_view: dict) -> str:
    from html import escape

    if plan_view.get('empty'):
        return (
            f'<div class="pa-aip-plan-board">'
            f'<p class="pa-aip-empty">{escape(str(plan_view.get("hint") or "尚无规划"))}</p>'
            f'</div>'
        )

    applied_cls = 'pa-aip-badge--ok' if plan_view.get('applied') else 'pa-aip-badge--muted'
    summary = escape(str(plan_view.get('summary') or '（无摘要）')).replace('\n', '<br/>')
    warnings = plan_view.get('warnings') or []
    warn_html = ''
    if warnings:
        items = ''.join(f'<li>{escape(w)}</li>' for w in warnings)
        warn_html = (
            f'<article class="pa-afc-card pa-aip-card pa-aip-card--warn">'
            f'<header class="pa-afc-card-head">'
            f'<h4 class="pa-afc-card-title">'
            f'<span class="pa-afc-dot" style="background:#f59e0b"></span>提示</h4>'
            f'</header>'
            f'<ul class="pa-aip-warn-list">{items}</ul>'
            f'</article>'
        )

    return (
        f'<div class="pa-aip-plan-board">'
        f'<article class="pa-afc-card pa-aip-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#818cf8"></span>规划概览</h4>'
        f'<span class="pa-aip-badge {applied_cls}">'
        f'{escape(str(plan_view.get("applied_label") or "—"))}</span>'
        f'</header>'
        f'<div class="pa-aip-meta-list">'
        f'{_cf_kv_row("生成时间", str(plan_view.get("at") or "—"), value_cls="muted")}'
        f'{_cf_kv_row("策略", str(plan_view.get("strategy_label") or "—"))}'
        f'</div>'
        f'</article>'
        f'<article class="pa-afc-card pa-aip-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#38bdf8"></span>规划摘要</h4>'
        f'</header>'
        f'<div class="pa-aip-summary">{summary}</div>'
        f'</article>'
        f'<article class="pa-afc-card pa-aip-card">'
        f'<header class="pa-afc-card-head">'
        f'<h4 class="pa-afc-card-title">'
        f'<span class="pa-afc-dot" style="background:#34d399"></span>具体改动'
        f' <span class="pa-aip-badge">{len(plan_view.get("commands") or [])} 条</span></h4>'
        f'</header>'
        f'{_aip_command_rows_html(plan_view.get("commands") or [])}'
        f'</article>'
        f'{warn_html}'
        f'</div>'
    )


def render_feature_locked_panel(
    task_command: str,
    reason: str,
    device_id: str,
    config=None,
) -> None:
    """Pro 套餐锁定页：Normal 用户可见任务入口但无法使用功能。"""
    from html import escape

    from module.proalas.feature_gate import (
        PLAN_LABEL,
        PROALAS_FEATURE_LOCK_ENABLED,
        TASK_DISPLAY_NAME,
        get_effective_plan,
    )

    if not PROALAS_FEATURE_LOCK_ENABLED:
        return

    feature_name = escape(TASK_DISPLAY_NAME.get(task_command, task_command))
    reason_html = escape(reason or '此功能需要 Pro 套餐。')
    plan = get_effective_plan(config) if config is not None else 'normal'
    plan_text = escape(PLAN_LABEL.get(plan, plan))
    device_text = escape(device_id or '—')

    put_html(
        f"""
<style>
.pa-lock-wrap {{
  background: linear-gradient(135deg, rgba(30,27,75,.55), rgba(15,23,42,.85));
  border: 1px solid rgba(167,139,250,.35);
  border-radius: 12px;
  padding: 18px 20px;
  margin: 0 0 16px;
}}
.pa-lock-icon {{ font-size: 28px; line-height: 1; margin-bottom: 8px; }}
.pa-lock-title {{ margin: 0 0 8px; font-size: 16px; font-weight: 700; color: #e9d5ff; }}
.pa-lock-reason {{ margin: 0 0 12px; font-size: 13px; line-height: 1.6; opacity: .92; }}
.pa-lock-meta {{
  display: flex; flex-wrap: wrap; gap: 10px 18px;
  font-size: 12px; opacity: .78; margin: 0 0 12px;
}}
.pa-lock-hint {{
  margin: 0; font-size: 12px; opacity: .72; line-height: 1.55;
  border-top: 1px solid rgba(148,163,184,.16); padding-top: 12px;
}}
.pa-lock-badge {{
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  background: rgba(167,139,250,.18); color: #ddd6fe; font-size: 11px; font-weight: 600;
}}
</style>
<div class="pa-lock-wrap">
  <div class="pa-lock-icon">🔒</div>
  <h3 class="pa-lock-title">{feature_name} · Pro 专属</h3>
  <p class="pa-lock-reason">{reason_html}</p>
  <div class="pa-lock-meta">
    <span>设备 <strong>{device_text}</strong></span>
    <span>当前套餐 <span class="pa-lock-badge">{plan_text}</span></span>
  </div>
  <p class="pa-lock-hint">
    升级 Pro 后请在侧栏打开「账户管理」确认套餐已生效，并重启 Alas 调度。
    测试阶段锁开关见 <code>module/proalas/feature_gate.py</code> 中的
    <code>PROALAS_FEATURE_LOCK_ENABLED</code>。
  </p>
</div>
        """
    )


_AIP_STRATEGY_DOT = {
    'conservative': '#818cf8',
    'aggressive': '#f97316',
    'innovative': '#a855f7',
}


def _aip_strategy_selector_css() -> str:
    return """
.pa-aip-strategy-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}
.pa-aip-strategy-card .pa-afc-card-head {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  gap: 6px; margin: 0 0 8px;
}
.pa-aip-strategy-card .pa-afc-card-title {
  margin: 0; font-size: 13px; font-weight: 600; color: #1e293b;
  display: flex; align-items: center; gap: 6px;
}
.pa-aip-strategy-card .pa-afc-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pa-aip-strategy-list {
  border: 1px solid #f1f5f9; border-radius: 8px; overflow: hidden;
  background: #fafbfc; display: flex; flex-direction: column; gap: 0 !important;
}
.pa-aip-strategy-list > * { margin: 0 !important; }
scope.pa-aip-strategy-item,
.pa-aip-strategy-item {
  display: flex !important; align-items: center !important; justify-content: space-between !important;
  gap: 10px !important; padding: 10px 12px !important; margin: 0 !important;
  border-bottom: 1px solid #f1f5f9 !important; background: #fff !important;
  min-height: 0 !important;
}
scope.pa-aip-strategy-item:last-child,
.pa-aip-strategy-item:last-child { border-bottom: none !important; }
scope.pa-aip-strategy-item--active,
.pa-aip-strategy-item--active { background: #eef2ff !important; }
.pa-aip-strategy-left {
  display: flex; align-items: center; gap: 10px; flex: 1 1 auto; min-width: 0;
}
.pa-aip-strategy-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pa-aip-strategy-name {
  display: block; font-size: 13px; font-weight: 700; color: #1e293b; line-height: 1.3;
}
.pa-aip-strategy-sub {
  display: block; font-size: 11px; color: #94a3b8; line-height: 1.35;
}
scope.pa-aip-strategy-actions,
.pa-aip-strategy-actions {
  display: flex !important; align-items: center !important; gap: 8px !important;
  flex: 0 0 auto; margin: 0 !important; padding: 0 !important;
}
scope.pa-aip-strategy-actions > *,
.pa-aip-strategy-actions > * {
  margin: 0 !important; flex: 0 0 auto !important; width: auto !important; max-width: none !important;
}
scope.pa-aip-strategy-actions .pywebio-row,
.pa-aip-strategy-actions .pywebio-row { margin: 0 !important; padding: 0 !important; gap: 8px !important; }
.pa-aip-strategy-item .btn,
.pa-aip-strategy-actions .btn {
  padding: 4px 10px !important; font-size: 12px !important;
  min-height: 28px !important; border-radius: 8px !important;
  line-height: 1.2 !important; margin: 0 !important;
  background: #fff !important; border: 1px solid #cbd5e1 !important;
  color: #475569 !important; box-shadow: none !important;
}
.pa-aip-strategy-item .btn:hover,
.pa-aip-strategy-actions .btn:hover {
  background: #f8fafc !important; border-color: #94a3b8 !important; color: #334155 !important;
}
.pa-aip-strategy-item .btn:focus,
.pa-aip-strategy-actions .btn:focus {
  box-shadow: 0 0 0 2px rgba(148,163,184,.35) !important;
}
.pa-aip-strategy-badge {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  background: #dcfce7; color: #15803d; font-size: 11px; font-weight: 700;
}
"""


def render_ai_planner_panel(device_id: str, config, task_args: dict | None = None) -> None:
    """AI 自动规划：开关 + 三档策略 + 结构化规划卡片（定时生成，不可手动触发）。"""
    from html import escape

    from pywebio.output import popup, put_button, put_html, put_row, put_scope, toast, use_scope
    from module.config.utils import filepath_config, read_file, write_file
    from module.proalas.ai_planner.plan_display import build_plan_view
    from module.proalas.ai_planner.settings import ai_planner_yaml_path, load_ai_planner_settings
    from module.proalas.ai_planner.strategies import STRATEGIES, normalize_strategy, strategy_label
    from module.proalas.ai_planner.strategy_switch import (
        check_strategy_change_allowed,
        effective_auto_apply,
        record_strategy_change,
        strategy_switch_hint,
    )
    from module.config.deep import deep_set

    task_args = task_args or {}
    config_data = config.data if hasattr(config, 'data') else config
    planner_on = bool(getattr(config, 'Scheduler_Enable', False))
    settings = load_ai_planner_settings(force=True)
    current = normalize_strategy(getattr(config, 'ProalasAiPlanner_Strategy', ''))
    plan_view = build_plan_view(device_id)
    yaml_path = ai_planner_yaml_path()
    switch_hint = strategy_switch_hint(config)
    auto_apply_on = effective_auto_apply(config)
    custom_event_main_on = bool(getattr(config, 'ProalasAiPlanner_CustomEventMain', False))

    def _save_strategy(strategy_id: str) -> bool:
        sid = normalize_strategy(strategy_id)
        path = filepath_config(device_id)
        data = read_file(path)
        if not isinstance(data, dict):
            toast('配置读取失败', color='error')
            return False
        if 'ProalasAiPlanner' not in data or not isinstance(data.get('ProalasAiPlanner'), dict):
            data['ProalasAiPlanner'] = {}
        deep_set(data, ['ProalasAiPlanner', 'Strategy'], sid)
        write_file(path, data)
        return True

    def _render_strategy_bar(active_id: str) -> None:
        from pywebio.output import put_column

        with use_scope('pa_aip_strategy_bar', clear=True):
            put_html(
                f"""
<style>{_aip_strategy_selector_css()}</style>
<article class="pa-aip-strategy-card">
  <header class="pa-afc-card-head">
    <h4 class="pa-afc-card-title">
      <span class="pa-afc-dot" style="background:#6366f1"></span>规划策略
    </h4>
    <span class="pa-aip-badge">{escape(switch_hint)}</span>
  </header>
                """
            )
            row_widgets = []
            for sid, meta in STRATEGIES.items():
                is_active = sid == active_id
                dot = _AIP_STRATEGY_DOT.get(sid, '#94a3b8')
                item_cls = 'pa-aip-strategy-item pa-aip-strategy-item--active' if is_active else 'pa-aip-strategy-item'
                label_html = put_html(
                    f'<div class="pa-aip-strategy-left">'
                    f'<span class="pa-aip-strategy-dot" style="background:{dot}"></span>'
                    f'<div>'
                    f'<strong class="pa-aip-strategy-name">{escape(meta["label"])}</strong>'
                    f'<span class="pa-aip-strategy-sub">{escape(meta.get("title") or "")}</span>'
                    f'</div></div>'
                )
                if is_active:
                    actions = put_row([
                        put_html('<span class="pa-aip-strategy-badge">当前</span>'),
                        put_button('说明', onclick=lambda s=sid: _help(s), outline=True, small=True),
                    ], size='auto auto').style('pa-aip-strategy-actions')
                else:
                    actions = put_row([
                        put_button('选用', onclick=lambda s=sid: _select(s), outline=True, small=True),
                        put_button('说明', onclick=lambda s=sid: _help(s), outline=True, small=True),
                    ], size='auto auto').style('pa-aip-strategy-actions')
                row_widgets.append(
                    put_row([label_html, actions], size='1fr auto').style(item_cls)
                )
            put_column(row_widgets).style('pa-aip-strategy-list')
            put_html('</article>')

    def _render_footer(active_id: str) -> None:
        with use_scope('pa_aip_strategy_foot', clear=True):
            put_html(
                f'<p class="pa-aip-foot">历史：./config/proalas/AiPlannerHistory.json'
                f' · TimerPlan 物化后串行规划，Scheduler 约 12h 补跑（10h 内去重）'
                f' · AutoApply={"开" if auto_apply_on else "关"}'
                f' · 活动主线自定义={"开" if custom_event_main_on else "关"}</p>'
            )

    def _select(strategy_id: str):
        nonlocal current
        sid = normalize_strategy(strategy_id)
        if sid == current:
            return
        ok, msg = check_strategy_change_allowed(config, device_id, sid)
        if not ok:
            toast(msg, color='warning')
            return
        if not _save_strategy(sid):
            return
        record_strategy_change(device_id, sid)
        current = sid
        _render_strategy_bar(current)
        _render_footer(current)
        toast(f'已切换为【{strategy_label(sid)}】策略（下次规划周期生效）', color='success')

    def _help(strategy_id: str):
        sid = normalize_strategy(strategy_id)
        meta = STRATEGIES[sid]
        popup(meta['title'], meta['help'].replace('\n', '<br/>'), size='large')

    put_html(
        f"""
<style>
{PA_LIGHT_CSS}
.pa-aip-wrap {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; margin: 0 0 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-aip-head {{ margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #1e293b; }}
.pa-aip-intro {{ margin: 0 0 12px; font-size: 12px; color: #64748b; line-height: 1.55; }}
.pa-aip-foot {{ font-size: 11px; color: #94a3b8; margin-top: 8px; }}
</style>
<div class="pa-aip-wrap">
  <h4 class="pa-aip-head">AI 自动规划</h4>
  <p class="pa-aip-intro">
    在下方<strong>启用 AI 自动规划</strong>后，由 <strong>TimerPlan（定时计划）物化完成</strong>与
    <strong>每 12 小时 Scheduler</strong> 自动生成，此处不可手动触发。
    当前：<span class="pa-aip-badge {'pa-aip-badge--ok' if planner_on else 'pa-aip-badge--muted'}">
    {'已启用' if planner_on else '已关闭'}</span>
    · 在下方列表选用策略；点「说明」查看详情。{escape(switch_hint)}。
    网关：<code>{escape(settings.gateway_url or '未配置')}</code>
    · {'已连接' if settings.configured else '未配置'} · 配置 <code>{escape(yaml_path)}</code>
  </p>
</div>
        """
    )

    put_html(
        '<p class="pa-tt-sub">规划总开关 · <code>ProalasAiPlanner</code>（AI 自动规划）</p>'
        '<p class="pa-tt-sub-hint">'
        '「启用该功能」= 是否参与调度：TimerPlan 结束后串行规划 + 约 12 小时独立补跑。'
        '关闭后仅保留本页策略与历史查看，不会调用网关。'
        '</p>'
    )
    sched_enable = _pa_scheduler_rows(
        'ProalasAiPlanner',
        task_args,
        config_data,
        scope_prefix='aip',
        fields=('Enable',),
    )
    if sched_enable is not None:
        sched_enable

    put_html(
        '<p class="pa-tt-sub">写回设置 · <code>ProalasAiPlanner</code></p>'
        '<p class="pa-tt-sub-hint">'
        '「定时规划自动写配置」= AutoApply：规划生成后是否直接改 config（Pro+ / 创新·人工 在代码里强制关闭）。'
        '「活动与主线自定义」开启后，规划将跳过对活动1/2、主线1/2（Event/Event2/Main/Main2）的修改。'
        '</p>'
    )
    apply_row = _pa_task_option_rows(
        'ProalasAiPlanner',
        task_args,
        config_data,
        scope_prefix='aip',
        field_order=('AutoApply', 'CustomEventMain'),
    )
    if apply_row is not None:
        apply_row

    put_scope('pa_aip_strategy_bar')
    _render_strategy_bar(current)

    put_html(
        f"""
<style>
.pa-aip-plan-board {{
  display: flex; flex-direction: column; gap: 10px;
  margin: 0 0 12px;
}}
.pa-aip-plan-board .pa-afc-card {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 10px 12px; box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}
.pa-aip-plan-board .pa-afc-card-head {{
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  gap: 6px; margin: 0 0 8px;
}}
.pa-aip-plan-board .pa-afc-card-title {{
  margin: 0; font-size: 13px; font-weight: 600; color: #1e293b;
  display: flex; align-items: center; gap: 6px;
}}
.pa-aip-plan-board .pa-afc-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.pa-aip-card {{ margin: 0; }}
.pa-aip-meta-list {{
  border: 1px solid #f1f5f9; border-radius: 8px; overflow: hidden; background: #fafbfc;
}}
.pa-aip-meta-list .pa-cf-kv {{
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; padding: 8px 10px; border-bottom: 1px solid #f1f5f9;
  font-size: 12px; line-height: 1.45;
}}
.pa-aip-meta-list .pa-cf-kv:last-child {{ border-bottom: none; }}
.pa-aip-meta-list .pa-cf-kv-key {{ color: #64748b; }}
.pa-aip-meta-list .pa-cf-kv-val {{ color: #1e293b; font-weight: 600; }}
.pa-aip-meta-list .pa-cf-kv-val--muted {{ color: #64748b; font-weight: 500; }}
.pa-aip-summary {{
  margin: 0; padding: 10px 12px;
  border: 1px solid #f1f5f9; border-radius: 8px; background: #fafbfc;
  font-size: 12px; line-height: 1.6; color: #334155;
}}
.pa-aip-badge {{
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  background: #f1f5f9; color: #64748b; font-size: 10px; font-weight: 700;
}}
.pa-aip-badge--ok {{ background: #dcfce7; color: #15803d; }}
.pa-aip-badge--muted {{ background: #f1f5f9; color: #64748b; }}
.pa-aip-cmd-list {{
  list-style: none; margin: 0; padding: 0;
  border: 1px solid #f1f5f9; border-radius: 8px; overflow: hidden;
}}
.pa-aip-cmd {{
  display: grid; grid-template-columns: 28px 72px 1fr auto auto;
  align-items: center; gap: 8px;
  padding: 8px 10px; border-bottom: 1px solid #f1f5f9;
  background: #fff; font-size: 12px; line-height: 1.4;
}}
.pa-aip-cmd:last-child {{ border-bottom: none; }}
.pa-aip-cmd:nth-child(even) {{ background: #fafbfc; }}
.pa-aip-cmd-idx {{
  font-size: 11px; font-weight: 700; color: #94a3b8; text-align: center;
}}
.pa-aip-cmd-kind {{
  font-size: 10px; font-weight: 700; color: #6366f1;
  background: rgba(99,102,241,.10); padding: 2px 6px; border-radius: 4px;
  text-align: center; white-space: nowrap;
}}
.pa-aip-cmd-target {{
  color: #1e293b; font-weight: 600; word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}}
.pa-aip-cmd-arrow {{ color: #cbd5e1; font-weight: 700; }}
.pa-aip-cmd-value {{
  color: #0f766e; font-weight: 700; white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}}
.pa-aip-empty {{
  margin: 0; padding: 16px; text-align: center;
  border: 1px dashed #cbd5e1; border-radius: 8px;
  background: #f8fafc; color: #64748b; font-size: 12px; line-height: 1.55;
}}
.pa-aip-warn-list {{
  margin: 0; padding: 8px 10px 8px 24px; font-size: 12px; color: #92400e; line-height: 1.5;
}}
@media (max-width: 720px) {{
  .pa-aip-cmd {{
    grid-template-columns: 24px 1fr;
    grid-template-areas:
      "idx kind"
      "target target"
      "value value";
  }}
  .pa-aip-cmd-idx {{ grid-area: idx; }}
  .pa-aip-cmd-kind {{ grid-area: kind; justify-self: start; }}
  .pa-aip-cmd-target {{ grid-area: target; }}
  .pa-aip-cmd-arrow {{ display: none; }}
  .pa-aip-cmd-value {{ grid-area: value; justify-self: start; color: #334155; }}
}}
</style>
<h4 class="pa-aip-head" style="margin:0 0 8px;font-size:13px;font-weight:700;color:#334155;">
  最新规划（只读）</h4>
{_render_ai_plan_board(plan_view)}
        """
    )

    put_scope('pa_aip_strategy_foot')
    _render_footer(current)

