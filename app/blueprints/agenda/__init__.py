from flask import Blueprint

bp = Blueprint("agenda", __name__, url_prefix="/agenda")

from . import routes  # noqa: E402,F401

