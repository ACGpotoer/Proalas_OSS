"""
Copy from pywebio.platform.fastapi
"""
import asyncio
import os
from pathlib import Path

import uvicorn
from pywebio.platform.fastapi import (STATIC_PATH, Session, cdn_validation,
                                      get_free_port,
                                      open_webbrowser_on_server_started,
                                      start_remote_access_service,
                                      webio_routes)
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


class HeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response


def asgi_app(
    applications,
    cdn=True,
    static_dir=None,
    img_dir=None,
    debug=False,
    allowed_origins=None,
    check_origin=None,
    **starlette_settings
):
    debug = Session.debug = os.environ.get("PYWEBIO_DEBUG", debug)
    cdn = cdn_validation(cdn, "warn")
    if cdn is False:
        cdn = "pywebio_static"
    routes = []
    if img_dir:
        img_dir = str(Path(img_dir).resolve())
        os.makedirs(img_dir, exist_ok=True)
        try:
            from module.logger import logger

            logger.info('ProAlas screenshot URL mount: /img -> %s', img_dir)
        except Exception:
            pass
        routes.append(
            Mount("/img", app=StaticFiles(directory=img_dir), name="proalas_img")
        )
    if static_dir:
        routes.append(
            Mount("/static", app=StaticFiles(directory=static_dir), name="static")
        )
    try:
        from module.proalas.instance_api import build_instance_routes

        routes.extend(build_instance_routes())
        try:
            from module.logger import logger as _logger

            _logger.info('mmc instance_api routes mounted')
        except Exception:
            pass
    except Exception as e:
        try:
            from module.logger import logger as _logger

            _logger.warning('mmc instance_api routes not loaded: %s', e)
        except Exception:
            pass
    routes.extend(
        webio_routes(
            applications,
            cdn=cdn,
            allowed_origins=allowed_origins,
            check_origin=check_origin,
        )
    )
    routes.append(
        Mount(
            "/pywebio_static",
            app=StaticFiles(directory=STATIC_PATH),
            name="pywebio_static",
        )
    )
    middleware = [Middleware(HeaderMiddleware)]
    return Starlette(
        routes=routes, middleware=middleware, debug=debug, **starlette_settings
    )


def start_server(
    applications,
    port=0,
    host="",
    cdn=True,
    static_dir=None,
    img_dir=None,
    remote_access=False,
    debug=False,
    allowed_origins=None,
    check_origin=None,
    auto_open_webbrowser=False,
    **uvicorn_settings
):

    app = asgi_app(
        applications,
        cdn=cdn,
        static_dir=static_dir,
        img_dir=img_dir,
        debug=debug,
        allowed_origins=allowed_origins,
        check_origin=check_origin,
    )

    if auto_open_webbrowser:
        asyncio.get_event_loop().create_task(
            open_webbrowser_on_server_started("localhost", port)
        )

    if not host:
        host = "0.0.0.0"

    if port == 0:
        port = get_free_port()

    if remote_access:
        start_remote_access_service(local_port=port)

    uvicorn.run(app, host=host, port=port, **uvicorn_settings)
