#!/usr/bin/env python3
"""roadmap.py: the one CLI for the roadmap dashboard. Data commands live in rm_data.py;
other rm_*.py modules (rm_tokens, rm_git, rm_map, rm_publish, rm_legacy) are imported if
present. A module adds commands by defining register(sub) (argparse subparsers) whose
commands set func(args, project), and may define selftest() (raise on failure).
"""
import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rm_data  # noqa: E402

MODULES = ["rm_data", "rm_tokens", "rm_git", "rm_activity", "rm_flow", "rm_map", "rm_tasks", "rm_publish", "rm_legacy"]
NOT_YET = {
    "tokens": "S3", "git": "S6", "map": "S7", "sync-shell": "S4", "init": "S4", "add-tab": "S4",
    "publish-args": "S4", "mark-published": "S4", "serve": "S4", "refresh": "S4", "migrate-legacy": "S2",
}


def load_modules():
    mods = []
    for name in MODULES:
        try:
            mods.append(importlib.import_module(name))
        except ModuleNotFoundError as e:
            if e.name != name:
                raise
    return mods


def not_implemented(story):
    def fn(args, project):
        raise rm_data.Err(f"{args.cmd} is not implemented yet (story {story})")
    return fn


def cmd_selftest(args, project):
    for m in load_modules():
        if hasattr(m, "selftest"):
            m.selftest()


def build(mods):
    ap = argparse.ArgumentParser(prog="roadmap.py", description="Roadmap dashboard CLI")
    ap.add_argument("--project", default=".", help="project directory (default .)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")
    for m in mods:
        if hasattr(m, "register"):
            m.register(sub)
    p = sub.add_parser("selftest", help="run every module's selftest in a temp project")
    p.set_defaults(func=cmd_selftest)
    for name, story in NOT_YET.items():
        if name not in sub.choices:
            p = sub.add_parser(name, help=f"not implemented yet (story {story})", add_help=False)
            p.add_argument("rest", nargs=argparse.REMAINDER)
            p.set_defaults(func=not_implemented(story))
    return ap


def main(argv=None):
    ap = build(load_modules())
    args = ap.parse_args(argv)
    try:
        args.func(args, Path(args.project).resolve())
    except rm_data.Err as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except AssertionError as e:
        print(f"selftest FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
