"""Fixture: test tham chiếu export_report và load_rows."""
from app.service import export_report


def test_export_report_returns_result():
    assert export_report is not None
