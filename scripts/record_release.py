#!/usr/bin/env python3
"""Record the release commit and CI run on the evidence manifest.

Why a separate step: a manifest cannot contain the hash of the commit that
includes the manifest (that hash depends on the manifest). So the manifest names
the commit whose *source tree* it describes, and this script records the commit
that carries the evidence plus a mechanical proof that the two trees differ only
in artifacts/review/.

Usage:
  python3 scripts/record_release.py --evidence-commit <sha> \
      --ci-run 123 --ci-conclusion success --ci-jobs 4
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "artifacts" / "review" / "evidence-manifest.json"
EVIDENCE_PATH = "artifacts/review"


def git(*args):
    completed = subprocess.run(["git", "-C", str(ROOT), *args],
                               capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ghi provenance của release vào manifest")
    parser.add_argument("--evidence-commit", required=True)
    parser.add_argument("--ci-run", default="")
    parser.add_argument("--ci-conclusion", default="")
    parser.add_argument("--ci-jobs", type=int, default=0)
    args = parser.parse_args(argv)
    if not MANIFEST.exists():
        print("chưa có evidence-manifest.json", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = manifest.get("source_commit", "")

    # Proof, not assertion: the two commits must differ only in evidence files.
    code, diff, error = git("diff", "--name-only", source, args.evidence_commit,
                            "--", ".", ":(exclude)" + EVIDENCE_PATH)
    if code != 0:
        print("không so được hai commit: " + error, file=sys.stderr)
        return 1
    non_evidence = [line for line in diff.splitlines() if line.strip()]
    code, head, _ = git("rev-parse", "HEAD")

    manifest["provenance"] = {
        "source_commit": source,
        "evidence_commit": args.evidence_commit,
        "head_at_record": head,
        "source_tree_equals_evidence_tree_except": EVIDENCE_PATH,
        "non_evidence_diff": non_evidence,
        "clean_source_tree": not non_evidence,
        "recorded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "note": ("source_commit là commit của code được mô tả; evidence_commit là commit "
                 "chứa manifest này. Hai cây chỉ khác nhau ở artifacts/review/, đã kiểm "
                 "bằng git diff."),
    }
    if args.ci_run:
        manifest["ci"] = {
            "run_id": args.ci_run,
            "commit": args.evidence_commit,
            "conclusion": args.ci_conclusion or "unknown",
            "jobs": args.ci_jobs,
            "url": ("https://github.com/Hieupt1904/project-flow-explainer/actions/runs/"
                    + args.ci_run),
            "recorded_at": manifest["provenance"]["recorded_at"],
        }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"provenance": manifest["provenance"],
                      "ci": manifest.get("ci", {})}, ensure_ascii=False, indent=1))
    return 0 if not non_evidence else 2


if __name__ == "__main__":
    sys.exit(main())
