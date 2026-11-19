#!/usr/bin/env python3
"""Record the CI run that proves the pushed commit on the evidence manifest.

The core never calls the network. This script is a release step: it takes the
values the operator read from CI and merges them into evidence-manifest.json.

Usage:
  python3 scripts/record_ci_run.py --run-id 44563079783 --commit 9195956 \
      --conclusion success --jobs 4
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "artifacts" / "review" / "evidence-manifest.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ghi CI run vào evidence manifest")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--conclusion", required=True,
                        choices=["success", "failure", "cancelled", "pending"])
    parser.add_argument("--jobs", type=int, default=0)
    parser.add_argument("--url", default="")
    args = parser.parse_args(argv)
    if not MANIFEST.exists():
        print("chưa có evidence-manifest.json; chạy scripts/regen_evidence.py trước",
              file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["ci"] = {
        "run_id": args.run_id,
        "commit": args.commit,
        "conclusion": args.conclusion,
        "jobs": args.jobs,
        "url": args.url or ("https://github.com/Hieupt1904/project-flow-explainer/actions/runs/" + args.run_id),
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": "CI chạy trên commit chứa chính manifest này; commit kế tiếp chỉ thêm run id.",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(manifest["ci"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
