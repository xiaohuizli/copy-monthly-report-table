#!/usr/bin/env python3
"""Build clipboard TSV from a Chinese monthly work-detail Markdown table."""

from __future__ import annotations

import argparse
import calendar
import ctypes
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from work_calendar import DEFAULT_CALENDAR, WorkCalendar


TSV_HEADERS = (
    "开发平台",
    "人员",
    "协作人员",
    "工作岗位",
    "工作内容",
    "预估天数",
    "开始时间",
    "完成时间",
    "完成状态",
)
TSV_CELL_TRANSLATION = str.maketrans("\t\r\n", "   ")


@dataclass
class WorkRow:
    platform: str
    content: str
    estimate: str
    start: str
    end: str
    status: str = ""
    collaborators: str = ""


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text()


def split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().removeprefix("|").removesuffix("|").split("|")]


def parse_markdown_table(text: str) -> list[WorkRow]:
    rows: list[WorkRow] = []
    headers: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = split_md_row(line)
        if not headers:
            headers = cells
            continue
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells))
        platform = normalize_platform(row.get("平台") or row.get("开发平台") or "")
        content = row.get("工作内容") or row.get("内容") or ""
        if not platform or not content:
            continue
        rows.append(
            WorkRow(
                platform=platform,
                content=clean_content(content),
                estimate=row.get("预估天数") or "",
                start=row.get("开始时间") or "",
                end=row.get("完成时间") or row.get("结束时间") or "",
                status=row.get("完成状态") or row.get("状态") or "",
                collaborators=clean_content(row.get("协作人员") or ""),
            )
        )
    return rows


def normalize_platform(value: str) -> str:
    # Preserve the user's platform names, including capitalization.
    return value.strip()


def clean_content(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace("\t", " ").replace("\r", "").replace("\n", " ")


def duration_value(estimate: str) -> Decimal:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:天|人日|工作日)?\s*", estimate)
    if not match:
        raise ValueError(f"Invalid estimate {estimate!r}; use a positive number of workdays, e.g. '3 天'")
    try:
        value = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid estimate {estimate!r}") from exc
    if value <= 0:
        raise ValueError(f"Estimate must be positive: {estimate!r}")
    return value


def resolve_window(month: str | None, start_date: str | None, end_date: str | None,
                   through_today: bool, today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    month_start = date.fromisoformat(f"{month}-01") if month else None
    first = date.fromisoformat(start_date) if start_date else month_start
    last = date.fromisoformat(end_date) if end_date else None
    if first is None:
        if through_today:
            first = today.replace(day=1)
        elif last:
            first = last.replace(day=1)
        else:
            raise ValueError("provide --start-date, --month, --end-date, or --through-today")
    if month_start and first.replace(day=1) != month_start:
        raise ValueError("--month and --start-date must refer to the same month")
    if through_today:
        if first.replace(day=1) != today.replace(day=1):
            raise ValueError("--through-today requires the current month in Asia/Shanghai")
        if last and last > today:
            raise ValueError("--end-date cannot be after today with --through-today")
        last = last or today
    last = last or first.replace(day=calendar.monthrange(first.year, first.month)[1])
    if first.replace(day=1) != last.replace(day=1):
        raise ValueError("Start and end dates must be within the same month")
    if last < first:
        raise ValueError("End date must be on or after start date")
    return first, last


def assign_dates(rows: list[WorkRow], first_day: date, last_day: date | None = None,
                 work_calendar: WorkCalendar | None = None, start_mode: str = "spread") -> None:
    last_day = last_day or first_day.replace(day=calendar.monthrange(first_day.year, first_day.month)[1])
    if first_day.replace(day=1) != last_day.replace(day=1) or last_day < first_day:
        raise ValueError("Scheduling window must be ordered and within one month")
    if start_mode not in ("spread", "shared"):
        raise ValueError("start_mode must be spread or shared")
    work_calendar = work_calendar or WorkCalendar()
    workdays = [
        date(first_day.year, first_day.month, day)
        for day in range(first_day.day, last_day.day + 1)
        if work_calendar.is_workday(date(first_day.year, first_day.month, day))
    ]
    if not workdays:
        raise ValueError("No workdays in the requested scheduling window")
    for index, row in enumerate(rows):
        duration = duration_value(row.estimate)
        span = int(duration.to_integral_value(rounding="ROUND_CEILING"))
        if span > len(workdays):
            raise ValueError(
                f"Row {index + 1} needs {span} workdays, but only {len(workdays)} are available before the cutoff"
            )
        # Each task has its own date range; ranges may overlap and estimates are not summed as calendar capacity.
        start_index = 0 if start_mode == "shared" else index % (len(workdays) - span + 1)
        row.start = workdays[start_index].isoformat()
        row.end = workdays[start_index + span - 1].isoformat()


def build_tsv(rows: list[WorkRow], person: str, role: str, status: str | None, include_header: bool) -> str:
    lines = ["\t".join(TSV_HEADERS)] if include_header else []
    for row in rows:
        cells = (
            row.platform,
            person,
            row.collaborators,
            role,
            row.content,
            row.estimate,
            row.start,
            row.end,
            clean_content(status or row.status or "完成"),
        )
        lines.append("\t".join(cell.translate(TSV_CELL_TRANSLATION) for cell in cells))
    return "\n".join(lines)


def copy_to_clipboard(text: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return
    if not sys.platform.startswith("win"):
        raise RuntimeError("Clipboard copy requires macOS pbcopy or Windows clipboard APIs; use --print-only here.")
    cf_unicode_text = 13
    gmem_moveable = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p

    data = text + "\0"
    size = len(data.encode("utf-16-le"))
    handle = kernel32.GlobalAlloc(gmem_moveable, size)
    if not handle:
        raise OSError("GlobalAlloc failed")
    locked = kernel32.GlobalLock(handle)
    if not locked:
        kernel32.GlobalFree(handle)
        raise OSError("GlobalLock failed")
    ctypes.memmove(locked, data.encode("utf-16-le"), size)
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise OSError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_unicode_text, handle):
            kernel32.GlobalFree(handle)
            raise OSError("SetClipboardData failed")
        handle = 0
    finally:
        user32.CloseClipboard()


DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.json"


def load_config(path: Path) -> dict[str, str]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    for key in config:
        if key not in ("person", "role"):
            raise ValueError(f"Unknown configuration field: {key}")
    for key, value in config.items():
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "\t\r\n"):
            raise ValueError(f"Configuration {key} must be a nonempty single-line string")
    return config


def identity_value(value: str | None, fallback: str) -> str:
    result = fallback if value is None else value
    if not result.strip() or any(c in result for c in "\t\r\n"):
        raise ValueError("Person and role must be nonempty single-line strings")
    return result.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy monthly report work-detail rows as spreadsheet TSV.")
    parser.add_argument("source", type=Path, help="Markdown file containing a platform work-detail table")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Identity defaults JSON (relative paths use current directory)")
    parser.add_argument("--person", help="Override configured person for this run")
    parser.add_argument("--role", help="Override configured role for this run")
    parser.add_argument("--month", help="Report month as YYYY-MM")
    parser.add_argument("--start-date", help="Earliest scheduling date as YYYY-MM-DD; dates stay in that month")
    parser.add_argument("--end-date", help="Latest scheduling date as YYYY-MM-DD, inclusive")
    parser.add_argument("--through-today", action="store_true", help="Schedule within the current month through today in Asia/Shanghai")
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR, help="Verified holiday/makeup-workday JSON calendar")
    parser.add_argument("--start-mode", choices=("spread", "shared"), default="spread",
                        help="spread rotates starts with overlap allowed; shared starts every task on the first workday")
    parser.add_argument("--status", help="Override all statuses; otherwise keep row statuses, falling back to 完成")
    parser.add_argument("--include-header", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        person = identity_value(args.person, config.get("person", "李晓辉"))
        role = identity_value(args.role, config.get("role", "后端"))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    rows = parse_markdown_table(read_text(args.source))
    if not rows:
        raise SystemExit(f"No work-detail rows found in {args.source}")
    try:
        first_day, last_day = resolve_window(args.month, args.start_date, args.end_date, args.through_today)
        for index, row in enumerate(rows, start=1):
            try:
                duration_value(row.estimate)
            except ValueError as exc:
                raise ValueError(f"Row {index} ({row.content}): {exc}") from exc
        assign_dates(rows, first_day, last_day, WorkCalendar(args.calendar), args.start_mode)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    tsv = build_tsv(rows, person, role, args.status, args.include_header)
    if args.print_only:
        print(tsv)
    else:
        copy_to_clipboard(tsv)
        print(f"Copied {len(rows)} rows to clipboard from {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
