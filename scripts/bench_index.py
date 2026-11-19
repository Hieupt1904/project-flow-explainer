#!/usr/bin/env python3
"""Benchmark the scanner and the index on a synthetic repository.

Why this exists: "repo lớn không OOM dễ dàng" is a claim that needs a number.
This script generates N files with a fixed seed, then measures scan time, index
build time, incremental rebuild time and peak RSS. It prints one JSON object.

Usage:
  python3 scripts/bench_index.py --files 1500 --json          # thư mục tạm, tự dọn
  python3 scripts/bench_index.py --files 1500 --dir <workdir> --json
No network, no third-party packages, and it never touches an existing repo.
"""

import argparse
import json
import os
import random
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for candidate in (str(HERE), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from pfe import facts, index  # noqa: E402

TEMPLATE = """// module {name}
const {{ db }} = require('./db')
const helper = require('./helper_{index}')

async function handle{index}(input) {{
  const rows = await db.query('SELECT id, total FROM table_{index} WHERE id = ?', [input])
  if (!rows.length) {{
    throw new Error('empty_{index}')
  }}
  return rows.map((row) => ({{ ...row, index }}))
}}

function fallback{index}(input) {{
  try {{
    return handle{index}(input)
  }} catch (error) {{
    return []
  }}
}}

module.exports = {{ handle{index}, fallback{index} }}
"""


def generate(target, count, seed=7):
    random.seed(seed)
    (target / "modules").mkdir(parents=True, exist_ok=True)
    (target / "db.js").write_text("const db = { query: async () => [] }\n"
                                  "module.exports = { db }\n", encoding="utf-8")
    for number in range(count):
        (target / "modules" / ("module_%04d.js" % number)).write_text(
            TEMPLATE.format(name=number, index=number), encoding="utf-8")


def rss_mb():
    """Peak resident set size of THIS process.

    /proc/self/status is preferred: ru_maxrss can inherit a pre-fork high-water
    mark from the process supervisor and then report a wildly inflated number.
    """
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        pass
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def run(workdir, count):
    repo = Path(workdir) / ("bench-%d" % count)
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    generate(repo, count)
    total_bytes = sum(path.stat().st_size for path in repo.rglob("*.js"))

    started = time.time()
    files, excluded, budget = facts.scan_repository(repo)
    scan_ms = round((time.time() - started) * 1000, 1)

    started = time.time()
    first = index.build_index(repo, mode="full")
    full_ms = round((time.time() - started) * 1000, 1)

    started = time.time()
    second = index.build_index(repo, mode="incremental")
    incremental_ms = round((time.time() - started) * 1000, 1)

    return {
        "files": count,
        "source_bytes": total_bytes,
        "scan_ms": scan_ms,
        "scan_files": len(files),
        "budget_notes": budget.notes,
        "index_full_ms": full_ms,
        "index_incremental_ms": incremental_ms,
        "files_parsed_full": first["files_parsed"],
        "files_parsed_incremental": second["files_parsed"],
        "entities": first["entities"],
        "facts": first["facts"],
        "db_bytes": index.db_path(repo).stat().st_size,
        "rss_mb": rss_mb(),
        "limits": {
            "max_files_scanned": facts.MAX_FILES_SCANNED,
            "max_total_source_bytes": facts.MAX_TOTAL_SOURCE_BYTES,
            "max_file_bytes": facts.MAX_FILE_BYTES,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark scanner + index")
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    workdir = args.dir or Path(tempfile.mkdtemp(prefix="pfe-bench-"))
    created = args.dir is None
    try:
        result = run(workdir, args.files)
    finally:
        if created:
            shutil.rmtree(workdir, ignore_errors=True)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for key, value in result.items():
            print("%-26s %s" % (key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
