"""Fixture: Flask blueprint — route khai báo qua @bp.route, không phải @app."""
from flask import Blueprint

bp = Blueprint("reports", __name__)


@bp.route("/reports/export")
def export_reports():
    rows = load_rows()
    return build_csv(rows)


@bp.get("/reports/status")
def report_status():
    return {"ok": True}


def load_rows():
    return []


def build_csv(rows):
    return ",".join(str(row) for row in rows)
