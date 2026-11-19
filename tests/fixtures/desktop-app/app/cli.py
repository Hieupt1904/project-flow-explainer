"""Fixture: CLI có subcommand thật (add_parser)."""
import argparse


def build_parser():
    parser = argparse.ArgumentParser(prog="qtoan")
    sub = parser.add_subparsers(dest="command")
    export = sub.add_parser("export", help="xuất Excel quyết toán")
    export.add_argument("--month", required=True)
    sub.add_parser("check", help="kiểm tra dữ liệu")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "export":
        return run_export(args.month)
    return 0


def run_export(month):
    return {"month": month}
