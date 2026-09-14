from flask import Blueprint

bp = Blueprint("products", __name__, url_prefix="/productos")

from . import routes  # noqa: E402,F401

