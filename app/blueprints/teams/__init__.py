from flask import Blueprint

bp = Blueprint("teams", __name__, url_prefix="/equipos")

from . import routes  # noqa: E402,F401

