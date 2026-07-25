"""Reverse-proxy Alas WebUI with session-locked device_id (sync httpx, for Flask)."""
import json
from typing import Tuple
from urllib.parse import urlencode

import httpx
from flask import Response, current_app, request, session

from proalas.device_cookie import get_device_id_from_cookie_header
from proalas.models_devices import list_config_device_ids


def _build_locked_ui_inject(allowed_config: str) -> str:
    cfg_dir = current_app.config["CONFIG_DIR"]
    all_configs = sorted(set(list_config_device_ids(cfg_dir)))
    allowed_json = json.dumps(allowed_config, ensure_ascii=False)
    config_list_json = json.dumps(all_configs, ensure_ascii=False)
    return f"""
<style>#alas-gateway-banner{{position:fixed;right:16px;bottom:16px;z-index:100000;
background:rgba(22,163,74,.95);color:#fff;padding:8px 12px;border-radius:8px;font-size:12px;}}</style>
<script>
(function(){{const allowedConfig={allowed_json};const allConfigs={config_list_json};
function hideWrong(){{document.querySelectorAll('a,button,li,[role=button],div,span').forEach(function(el){{
const t=(el.textContent||'').trim();if(!t||t.length>32||!allConfigs.includes(t))return;
const c=el.closest('a,button,li,[role=button]')||el;if((c.textContent||'').trim()!==t)return;
c.style.display=(t===allowedConfig)?'':'none';}});}}
function openIfNeeded(){{for(const el of document.querySelectorAll('a,button,li,[role=button],div,span')){{
const t=(el.textContent||'').trim();if(t!==allowedConfig)continue;const c=el.closest('a,button,li,[role=button]')||el;
if(c.style.display!=='none'){{c.click();break;}}}}}}
window.addEventListener('message',function(ev){{if(ev&&ev.data&&ev.data.type==='dap:focus-config'){{hideWrong();openIfNeeded();}}}});
function boot(){{hideWrong();openIfNeeded();}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
setInterval(function(){{hideWrong();openIfNeeded();}},800);
if(!document.getElementById('alas-gateway-banner')){{const d=document.createElement('div');
d.id='alas-gateway-banner';d.textContent='已锁定配置: '+allowedConfig;document.body.appendChild(d);}}
}})();
</script>
"""


def _override_json_body(raw: bytes, allowed: str) -> Tuple[bytes, bool]:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return raw, False
    if not isinstance(obj, dict):
        return raw, False
    changed = False
    for k in ("config", "config_name", "configName", "filename", "profile"):
        if k in obj and obj[k] != allowed:
            obj[k] = allowed
            changed = True
    if not changed:
        return raw, False
    return json.dumps(obj, ensure_ascii=False).encode("utf-8"), True


def _query_dict_override(allowed: str) -> str:
    d = {}
    for k in request.args.keys():
        vs = request.args.getlist(k)
        d[k] = vs[0] if len(vs) == 1 else vs
    for k in ("config", "config_name", "configName", "filename", "profile"):
        if k in d:
            d[k] = allowed
    return urlencode(d, doseq=True)


def proxy_upstream(subpath: str):
    allowed = get_device_id_from_cookie_header(
        request.headers.get("Cookie"), current_app.secret_key
    ) or session.get("device_id")
    if not allowed:
        return Response("Unauthorized", status=401)
    from proalas.account_expiry import device_is_expired

    if device_is_expired(current_app.config["CONFIG_DIR"], allowed):
        return Response("服务已过期", status=403)

    upstream_base = current_app.config["ALAS_UPSTREAM"].rstrip("/")
    path = subpath.strip("/") if subpath else ""
    url = f"{upstream_base}/{path}" if path else f"{upstream_base}/"
    if request.query_string:
        qs = _query_dict_override(allowed)
        url = f"{url}?{qs}"

    headers = {k: v for k, v in request.headers if k.lower() not in ("host", "connection")}
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = request.get_data()
        ct = request.content_type or ""
        if "application/json" in ct and body:
            body, _ = _override_json_body(body, allowed)

    try:
        with httpx.Client(
            timeout=httpx.Timeout(60.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            r = client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
    except httpx.ConnectError as e:
        return Response(
            f"<html><body>无法连接 Alas: {upstream_base}<br/>原因: {e}</body></html>",
            status=502,
            mimetype="text/html",
        )
    except httpx.HTTPError as e:
        return Response(
            f"<html><body>Alas 代理错误: {upstream_base}<br/>原因: {e}</body></html>",
            status=502,
            mimetype="text/html",
        )

    ct = r.headers.get("content-type", "")
    skip_h = {
        "content-length",
        "transfer-encoding",
        "x-frame-options",
        "content-security-policy",
    }
    out_headers = [(k, v) for k, v in r.headers.items() if k.lower() not in skip_h]
    if ct.startswith("text/html"):
        html = r.text
        inj = _build_locked_ui_inject(allowed)
        if "</body>" in html:
            html = html.replace("</body>", inj + "</body>")
        else:
            html += inj
        return Response(html, status=r.status_code, headers=out_headers)

    return Response(
        r.content,
        status=r.status_code,
        headers=out_headers,
        mimetype=ct.split(";")[0].strip() or None,
    )
