"""Regression coverage for cutoff dates, holiday calendars, and overlapping tasks."""

from datetime import date
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from copy_monthly_report_table import WorkRow, assign_dates, resolve_window
from work_calendar import WorkCalendar


def rows(*estimates):
    return [WorkRow("AI营销", f"任务 {i}", estimate, "", "") for i, estimate in enumerate(estimates)]


class SchedulingTests(unittest.TestCase):
    def test_current_month_through_today(self):
        self.assertEqual(resolve_window(None, None, None, True, date(2026, 10, 23)),
                         (date(2026, 10, 1), date(2026, 10, 23)))
        data = rows("13 天")
        assign_dates(data, date(2026, 10, 1), date(2026, 10, 23))
        self.assertEqual((data[0].start, data[0].end), ("2026-10-08", "2026-10-23"))

    def test_holidays_and_makeup_weekends(self):
        cal = WorkCalendar()
        for day in [date(2026, 10, i) for i in range(1, 8)] + [date(2026, 10, 11)]:
            self.assertFalse(cal.is_workday(day))
        for day in [date(2026, 10, 10), date(2026, 1, 4), date(2026, 5, 9)]:
            self.assertTrue(cal.is_workday(day))
        data = rows("3 天", "4 天")
        assign_dates(data, date(2026, 10, 8), date(2026, 10, 23), start_mode="shared")
        self.assertEqual([row.end for row in data], ["2026-10-10", "2026-10-12"])

    def test_same_day_tasks_and_effort_exceeding_capacity(self):
        data = rows(*(["1 天"] * 50))
        assign_dates(data, date(2026, 10, 1), date(2026, 10, 23), start_mode="shared")
        self.assertEqual({(row.start, row.end) for row in data}, {("2026-10-08", "2026-10-08")})
        assign_dates(data, date(2026, 10, 1), date(2026, 10, 23))
        self.assertTrue(all(row.end <= "2026-10-23" for row in data))
        self.assertLess(len({row.start for row in data}), len(data))

    def test_weekend_cutoff_and_fractional_estimate(self):
        first, last = resolve_window(None, None, None, True, date(2026, 10, 11))
        data = rows("2.5 天")
        assign_dates(data, first, last)
        self.assertEqual((data[0].start, data[0].end), ("2026-10-08", "2026-10-10"))
        self.assertEqual(data[0].estimate, "2.5 天")

    def test_full_month_and_explicit_cutoff(self):
        self.assertEqual(resolve_window("2026-10", None, None, False),
                         (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(resolve_window(None, None, "2026-10-23", False),
                         (date(2026, 10, 1), date(2026, 10, 23)))

    def test_invalid_windows(self):
        for args in [("2026-09", None, None, True),
                     ("2026-10", None, "2026-10-24", True),
                     ("2026-10", "2026-09-01", None, False),
                     ("2026-10", None, "2026-11-01", False),
                     (None, "2026-10-23", "2026-10-08", False)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                resolve_window(*args, today=date(2026, 10, 23))

    def test_no_workdays_excess_duration_and_missing_year(self):
        for first, last, estimate, message in [
            (date(2026, 10, 1), date(2026, 10, 7), "1", "No workdays"),
            (date(2026, 10, 1), date(2026, 10, 23), "14", "Row 1 needs 14 workdays"),
            (date(2027, 10, 1), date(2027, 10, 23), "1", "Missing verified work calendar")]:
            with self.assertRaisesRegex(ValueError, message):
                assign_dates(rows(estimate), first, last)

    def test_print_only_cli_and_failure_before_clipboard(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "work.md"
            source.write_text("| 平台 | 工作内容 | 预估天数 |\n| --- | --- | --- |\n"
                              "| AI营销 | A工作 | 1 天 |\n| AI营销 | B工作 | 1 天 |\n")
            script = Path(__file__).with_name("copy_monthly_report_table.py")
            base = [sys.executable, str(script), str(source), "--month", "2026-10",
                    "--start-mode", "shared", "--print-only"]
            result = subprocess.run(base + ["--end-date", "2026-10-23"], capture_output=True, text=True, check=True)
            lines = [line.split("\t") for line in result.stdout.splitlines()]
            self.assertEqual(len(lines), 2)
            self.assertTrue(all(len(line) == 8 and line[5:7] == ["2026-10-08", "2026-10-08"] for line in lines))
            result = subprocess.run(base + ["--end-date", "2026-10-07"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
