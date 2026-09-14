from flask import Blueprint

bp = Blueprint("users", __name__, url_prefix="/usuarios")

from . import routes  # noqa: E402,F401

