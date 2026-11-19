"""Fixture: worker xuất báo cáo định kỳ (Python) cho test build_flow."""
import csv
import os


def export_report_job(report_id, target_dir="/tmp"):
    rows = load_rows(report_id)
    if not rows:
        raise ValueError("report_empty")
    target = os.path.join(target_dir, f"report-{report_id}.csv")
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return target


def load_rows(report_id):
    return []
