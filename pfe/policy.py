"""Read/write policy: repository root, artifact root, slugs and atomic writes.

Every rule here is fail-closed:

  * artifact output exists only at `<repo>/artifacts/flows/<slug>/`;
  * a symlinked `artifacts`/`flows` that escapes the repository is refused
    before anything is created;
  * an artifact directory is fully written in a staging directory and only then
    renamed into place, so a failure never leaves a half-written flow behind;
  * slugs are restricted to `[A-Za-z0-9._-]` and never contain a path.
"""

import os
import re
import secrets
import shutil
from contextlib import contextmanager
from pathlib import Path

ARTIFACT_SUBDIR = ("artifacts", "flows")
SLUG_MAX = 48
SLUG_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


class BuildError(Exception):
    """A request the core refuses to serve, with a stable machine code."""

    def __init__(self, code, message, hint=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def as_dict(self):
        return {"status": "error", "code": self.code,
                "message": self.message, "hint": self.hint}


def real_dir(path, code, label):
    try:
        resolved = Path(os.path.realpath(str(path)))
    except OSError as error:
        raise BuildError(code, f"Không đọc được {label}: {path}", str(error))
    if not resolved.exists():
        raise BuildError(code, f"Không thấy {label}: {resolved}")
    if not resolved.is_dir():
        raise BuildError(code, f"{label} không phải thư mục: {resolved}")
    return resolved


def is_inside(root, target):
    root = str(root)
    target = str(target)
    return target == root or target.startswith(root + os.sep)


def artifact_root_for(root):
    """Return `<root>/artifacts/flows` and refuse a symlink pointing outside."""
    real_root = Path(os.path.realpath(str(root)))
    candidate = real_root.joinpath(*ARTIFACT_SUBDIR)
    probe = real_root
    for part in ARTIFACT_SUBDIR:
        probe = probe / part
        if probe.is_symlink():
            target = Path(os.path.realpath(str(probe)))
            if not is_inside(real_root, target):
                raise BuildError(
                    "artifact_symlink_escape",
                    f"Thư mục artifact là symlink ra ngoài repository: {probe} → {target}",
                    f"Chỉ cho phép artifact dưới {real_root.joinpath(*ARTIFACT_SUBDIR)}",
                )
    resolved = Path(os.path.realpath(str(candidate))) if candidate.exists() else candidate
    if not is_inside(real_root, resolved):
        raise BuildError(
            "invalid_artifact_root",
            f"Artifact root phải nằm trong repository: {resolved}",
            f"Dùng đúng {real_root.joinpath(*ARTIFACT_SUBDIR)}",
        )
    return candidate


def validate_out_dir(root, out_dir):
    """The only accepted artifact root is `<repo>/artifacts/flows`."""
    expected = artifact_root_for(root)
    if out_dir is None:
        return expected
    if not isinstance(out_dir, (str, os.PathLike)):
        raise BuildError(
            "invalid_argument_type",
            f"output_directory phải là chuỗi đường dẫn, nhận được {type(out_dir).__name__}",
            "Bỏ trống để dùng mặc định, hoặc truyền 'artifacts/flows'.",
        )
    raw = Path(out_dir).expanduser()
    candidate = raw if raw.is_absolute() else Path(root) / raw
    resolved = Path(os.path.realpath(str(candidate)))
    expected_real = Path(os.path.realpath(str(expected)))
    if resolved != expected_real:
        raise BuildError(
            "invalid_artifact_root",
            f"output directory không hợp lệ: {out_dir}",
            f"Chỉ chấp nhận {expected} (artifact không được ghi vào repo root, src, docs, tmp hay ngoài repo).",
        )
    if expected.is_symlink():
        raise BuildError("artifact_symlink_escape", f"Artifact root là symlink: {expected}")
    return expected


def safe_slug(slug):
    if slug is None:
        return None
    if not isinstance(slug, str):
        raise BuildError(
            "invalid_argument_type",
            f"slug phải là chuỗi, nhận được {type(slug).__name__}",
            "Bỏ trống để tool tự sinh slug.",
        )
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    if (not cleaned or cleaned in {".", ".."} or cleaned != slug.strip()
            or not SLUG_SAFE.match(cleaned)):
        raise BuildError(
            "invalid_slug",
            f"slug không hợp lệ: {slug!r}",
            "slug chỉ nhận chữ, số, dấu chấm, gạch dưới, gạch ngang.",
        )
    return cleaned[:SLUG_MAX]


@contextmanager
def staging_directory(artifacts_root, slug, reserved):
    """Write the whole artifact set in `.staging-*`, then rename it into place.

    `reserved` is the set of existing artifact names; the rename is the
    authoritative concurrency check (a directory cannot be renamed onto a
    non-empty directory), so two callers with the same slug cannot both win.
    The staging directory is always removed, including after a failure.
    """
    artifacts_root = Path(artifacts_root)
    final = artifacts_root / slug
    if final.exists() or slug in reserved:
        raise BuildError("artifact_exists", f"Thư mục artifact đã tồn tại: {slug}",
                         "Bỏ --slug để tự sinh tên mới, hoặc chọn slug khác.")
    artifacts_root.mkdir(parents=True, exist_ok=True)
    staging = artifacts_root / f".staging-{slug}-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        staging.mkdir(parents=False, exist_ok=False)
    except OSError as error:
        raise BuildError("artifact_write_failed", f"Không tạo được thư mục staging: {error}")
    try:
        yield staging
        try:
            os.rename(staging, final)
        except OSError as error:
            if final.exists():
                raise BuildError("artifact_exists",
                                 f"Thư mục artifact vừa được tạo bởi tiến trình khác: {slug}") from error
            raise BuildError("artifact_write_failed",
                             f"Không chuyển được artifact vào {slug}: {error}") from error
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def artifact_names(artifacts_root):
    try:
        return {entry.name for entry in Path(artifacts_root).iterdir() if entry.is_dir()}
    except OSError:
        return set()
