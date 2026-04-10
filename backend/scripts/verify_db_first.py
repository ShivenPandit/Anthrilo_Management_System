"""Run DB-first backfill windows and readiness validation gates.

Usage examples:
  python scripts/verify_db_first.py
  python scripts/verify_db_first.py --windows 7,30,90 --profile incremental
  python scripts/verify_db_first.py --skip-backfill --profile realtime_trigger
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator


def _parse_windows(raw: str) -> List[int]:
    windows = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
    return [value for value in windows if value > 0]


def _parse_date_boundary(value: Optional[str], end_of_day: bool) -> Optional[datetime]:
    if not value:
        return None

    parsed = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed.replace(tzinfo=timezone.utc)


async def _run(args: argparse.Namespace) -> int:
    orchestrator = get_unicommerce_sync_orchestrator()
    output = {
        "success": True,
        "windows": None,
        "profile": None,
        "readiness": None,
    }

    if not args.skip_backfill:
        windows = _parse_windows(args.windows)
        if not windows:
            raise ValueError("At least one positive backfill window is required")
        output["windows"] = await orchestrator.run_backfill_windows(windows)
        output["success"] = output["success"] and bool(output["windows"].get("success"))

    if args.profile:
        from_date = _parse_date_boundary(args.from_date, end_of_day=False)
        to_date = _parse_date_boundary(args.to_date, end_of_day=True)
        output["profile"] = await orchestrator.run_profile(args.profile, from_date, to_date)
        output["success"] = output["success"] and bool(output["profile"].get("success"))

    output["readiness"] = orchestrator.get_release_readiness()
    output["success"] = output["success"] and bool(output["readiness"].get("overall_passed"))

    print(json.dumps(output, indent=2, default=str))

    if args.no_fail_on_gates:
        return 0
    return 0 if output["success"] else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify DB-first pipeline readiness")
    parser.add_argument(
        "--windows",
        default="7,30,90,365",
        help="Comma-separated backfill windows in days",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Skip running backfill windows",
    )
    parser.add_argument(
        "--profile",
        choices=["incremental", "realtime_trigger", "full_backfill"],
        help="Optional sync profile to run before readiness checks",
    )
    parser.add_argument("--from-date", help="YYYY-MM-DD (required for full_backfill)")
    parser.add_argument("--to-date", help="YYYY-MM-DD (required for full_backfill)")
    parser.add_argument(
        "--no-fail-on-gates",
        action="store_true",
        help="Always exit 0 even when readiness gates fail",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.profile == "full_backfill" and (not args.from_date or not args.to_date):
        parser.error("--from-date and --to-date are required when --profile=full_backfill")

    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
