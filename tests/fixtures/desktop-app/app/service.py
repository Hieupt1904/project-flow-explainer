"""Fixture: lớp nghiệp vụ đọc/ghi dữ liệu quyết toán."""
from app.worker import export_job


def load_rows(month):
    sql = "SELECT id, total FROM payroll WHERE month = ?"
    return query(sql, [month])


def export_report(month):
    rows = load_rows(month)
    if not rows:
        raise LookupError("no_rows")
    return export_job(month)


def query(sql, params):
    return []
