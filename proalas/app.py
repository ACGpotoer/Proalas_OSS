import os
from pathlib import Path

from flask import Flask

from proalas.config import Config
from proalas.db import close_db, init_db
from proalas.models_devices import sync_devices_from_config

from proalas.routes import admin_bp, auth_bp, main_bp, pro_bp
from proalas.routes.proxy import bp as proxy_bp


def create_app(mount_alas_proxy: bool = True):
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
        # 避免与 Alas 根路径 /static 冲突；ASGI 会把上游 /static 单独代理
        static_url_path="/proalas-assets",
    )
    app.config.from_object(Config)
    # 本地改模板后免重启也能生效（uvicorn reload=False）
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    # Electron iframe(file://→http) 下默认 Cookie 易被拦；顶层打开后这些设置正常生效
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_PATH", "/")
    app.config.setdefault("REMEMBER_COOKIE_SAMESITE", "Lax")

    init_db(app)
    with app.app_context():
        from proalas.db import get_db

        with get_db() as conn:
            sync_devices_from_config(conn, app.config["CONFIG_DIR"])

    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(pro_bp)
    # 开源本地版不注册管理员/续费后台
    if os.environ.get("PROALAS_ENABLE_ADMIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        app.register_blueprint(admin_bp)
    if mount_alas_proxy:
        app.register_blueprint(proxy_bp)

    from proalas.pause_scheduler import start_pause_scheduler

    start_pause_scheduler(app)

    return app
