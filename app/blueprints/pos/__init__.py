from flask import Blueprint

bp = Blueprint("pos", __name__, url_prefix="/pos")

from . import routes  # noqa: E402,F401

