#!/usr/bin/env python3
"""Regenerate the three sample flows that ship in artifacts/samples/.

Sample layout (public, committed):

    artifacts/samples/shop/{flow.json,flow.html,overview.md,run.json}
    artifacts/samples/self/...
    artifacts/samples/empty/...

Everything is produced by the real CLI from HEAD, copied out of the analysed
repository so the samples never nest one artifacts directory inside another.

Usage: python3 scripts/regen_samples.py [--json]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "artifacts" / "samples"
CLI = ROOT / "scripts" / "build_flow.py"

SHOP_REQUEST = "Giải thích từ lúc người dùng nhấn xuất báo cáo đến khi nhận được file"
SELF_REQUEST = "Giải thích từ lúc người dùng chạy build_flow trên một repository đến khi nhận flow.json"
EMPTY_REQUEST = "luồng thanh toán thẻ tín dụng quốc tế"


def run_flow(repo, request):
    out = subprocess.run(
        [sys.executable, str(CLI), "--repo", str(repo), "--request", request, "--json"],
        capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit("CLI thất bại: " + out.stderr.strip())
    return json.loads(out.stdout)


def copy_artifacts(result, target):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    copied = []
    for value in result["paths"].values():
        source = Path(value)
        destination = target / source.name
        shutil.copy2(source, destination)
        copied.append(destination.relative_to(ROOT).as_posix())
    return copied


def main(argv=None):
    parser = argparse.ArgumentParser(description="Regenerate sample flows")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="pfe-samples-"))
    summary = {}
    try:
        shop = work / "shop-app"
        shutil.copytree(ROOT / "tests" / "fixtures" / "shop-app", shop,
                        ignore=shutil.ignore_patterns("artifacts", ".pfe", "__pycache__"))
        (shop / ".env").write_text("API_KEY=fixture-secret-value-abc123\n", encoding="utf-8")
        summary["shop"] = copy_artifacts(run_flow(shop, SHOP_REQUEST), SAMPLES / "shop")

        self_repo = work / "project-flow-explainer"
        shutil.copytree(ROOT, self_repo, ignore=shutil.ignore_patterns(
            "artifacts", ".pfe", "dist", "node_modules", "__pycache__", ".git", ".pytest_cache"))
        summary["self"] = copy_artifacts(run_flow(self_repo, SELF_REQUEST), SAMPLES / "self")

        empty = work / "empty-repo"
        empty.mkdir()
        (empty / "app.js").write_text("console.log('không có luồng nào ở đây')\n",
                                      encoding="utf-8")
        summary["empty"] = copy_artifacts(run_flow(empty, EMPTY_REQUEST), SAMPLES / "empty")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        for name, files in summary.items():
            print(name + ": " + ", ".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
