from flask import Blueprint

from proalas.proxy_alas import proxy_upstream

bp = Blueprint("proxy", __name__, url_prefix="/alas")


@bp.route("/", defaults={"subpath": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@bp.route("/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def alas_embed(subpath: str):
    return proxy_upstream(subpath)
