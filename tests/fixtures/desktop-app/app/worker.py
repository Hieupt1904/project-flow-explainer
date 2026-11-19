"""Fixture: worker chạy nền bằng decorator task."""
JOBS = []


def task(fn):
    JOBS.append(fn.__name__)
    return fn


@task
def export_job(month):
    if not month:
        raise ValueError("month_required")
    return {"month": month}
