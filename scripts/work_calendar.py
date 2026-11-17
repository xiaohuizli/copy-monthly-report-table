"""Read verified China holiday and makeup-workday calendars."""

import json
from datetime import date, timedelta
from pathlib import Path


DEFAULT_CALENDAR = Path(__file__).resolve().parent.parent / "references" / "china-work-calendar.json"


class WorkCalendar:
    def __init__(self, path: Path = DEFAULT_CALENDAR):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.years = {int(year) for year in data}
        self.holidays = set()
        self.workdays = set()
        for year, entry in data.items():
            if not entry.get("source"):
                raise ValueError(f"Calendar {year} requires an official source")
            for first, last in entry["holiday_ranges"]:
                start, end = date.fromisoformat(first), date.fromisoformat(last)
                if start > end or start.year != int(year) or end.year != int(year):
                    raise ValueError(f"Invalid holiday range: {first} to {last}")
                self.holidays.update(start + timedelta(days=i) for i in range((end - start).days + 1))
            for value in entry["workdays"]:
                day = date.fromisoformat(value)
                if day.year != int(year):
                    raise ValueError(f"Workday {value} does not belong to {year}")
                self.workdays.add(day)
        if self.holidays & self.workdays:
            raise ValueError("Calendar has conflicting holiday and workday dates")

    def is_workday(self, day: date) -> bool:
        if day.year not in self.years:
            raise ValueError(f"Missing verified work calendar for {day.year}; supply --calendar with official holiday and makeup-workday data")
        return day in self.workdays or (day.weekday() < 5 and day not in self.holidays)
