from flask import Blueprint

bp = Blueprint("settings", __name__, url_prefix="/configuracion")

from . import routes  # noqa: E402,F401

