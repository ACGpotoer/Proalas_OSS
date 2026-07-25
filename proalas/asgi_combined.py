"""
ASGI 入口：
- /alas       Alas 页面 + WebSocket
- /remote     （遗留）旧 ws-scrcpy 反代；当前远控走 Flask /app/pro/remote/*
- /api        （遗留）旧远控绝对路径反代
- /pywebio_static、/static、/img  指向上游（HTML 内绝对路径，否则会 404）
- 其余        Flask（静态在 /proalas-assets）
- 兜底 WS 中间件：避免绝对路径 WebSocket 打进 Flask 触发 AssertionError
"""
from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount

from proalas.app import create_app
from proalas.asgi_alas import build_alas_app, build_upstream_prefix_app
from proalas.asgi_remote import (
    ActiveRemoteWebSocketMiddleware,
    build_api_proxy_routes,
    build_remote_app,
)

_flask = create_app(mount_alas_proxy=False)
_alas = build_alas_app()
_remote = build_remote_app()
_pywebio_static = build_upstream_prefix_app("pywebio_static")
_alas_static = build_upstream_prefix_app("static")
_alas_img = build_upstream_prefix_app("img")

_starlette = Starlette(
    routes=[
        Mount("/alas", app=_alas),
        Mount("/remote", app=_remote),
        *build_api_proxy_routes(),
        Mount("/pywebio_static", app=_pywebio_static),
        Mount("/static", app=_alas_static),
        Mount("/img", app=_alas_img),
        Mount("/", app=WSGIMiddleware(_flask)),
    ],
)

application = ActiveRemoteWebSocketMiddleware(_starlette)
