import argparse
import json
import sys
from .constraints import CONSTRAINTS
from .router import INTENTS, MODES, route


def emit(data):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(prog="python -m harness100", description="Harness-100 v3.1-cc")
    commands = parser.add_subparsers(dest="command", required=True)
    r = commands.add_parser("route", help="classify a request (no side effects except safe project reads)")
    r.add_argument("--request", required=True)
    r.add_argument("--project")
    r.add_argument("--mode", choices=MODES)
    r.add_argument("--intent", choices=INTENTS, default="auto")
    r.add_argument("--test-result", choices=("passed", "failed", "unknown"), default="unknown")
    r.add_argument("--score", action="store_true")
    r.add_argument("--constraint", action="append", default=[], choices=CONSTRAINTS,
                   help="host-supplied restriction; can only narrow")
    g = commands.add_parser("git-status", help="side-effect-free git status of an untrusted repository")
    g.add_argument("project")
    led = commands.add_parser("ledger", help="task-wide validation ledger")
    led.add_argument("action", choices=("status", "record"))
    led.add_argument("--task-id", required=True)
    led.add_argument("--status", choices=("PASS", "FAIL", "미검증"))
    led.add_argument("--evidence")
    led.add_argument("--note", default="")
    q = commands.add_parser("qgate", help="re-execute checks and score from the raw log it produced")
    q.add_argument("--out", required=True)
    q.add_argument("--zip")
    q.add_argument("--expect-suite-sha256")
    args = parser.parse_args()
    try:
        if args.command == "route":
            emit(route(args.request, project=args.project, mode=args.mode, intent=args.intent,
                       test_result=args.test_result, score=args.score, constraints=args.constraint))
        elif args.command == "git-status":
            from .safe_git import status
            emit(status(args.project))
        elif args.command == "ledger":
            from .ledger import LedgerStore, LedgerError
            store = LedgerStore()
            if args.action == "status":
                result = store.status(args.task_id)
                emit(result)
                return 0 if result.get("enforced") else 3
            try:
                emit(store.record(args.task_id, args.status, args.evidence, args.note))
            except (LedgerError, ValueError, OSError) as error:
                emit({"recorded": False, "enforced": False, "reason": str(error)})
                return 3
        elif args.command == "qgate":
            from .qgate import run_gate
            report = run_gate(args.out, zip_path=args.zip, expect_suite=args.expect_suite_sha256)
            emit({k: report[k] for k in ("total", "overall", "fail_count", "unverified_count", "raw_log",
                                         "raw_sha256", "suite_sha256", "suite_pinned")})
            return 0 if report["overall"] == "완전 성공" else 1
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
