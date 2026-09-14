from flask import Blueprint

bp = Blueprint("tournaments", __name__, url_prefix="/torneos")

from . import routes  # noqa: E402,F401

