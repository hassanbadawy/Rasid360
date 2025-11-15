"""
Analytics Database Schema and Aggregation Logic
Separate database for pre-aggregated dashboard metrics to reduce load on main frigate.db
Updated every 5 minutes by analytics_scheduler.py
"""

import datetime
import logging
from peewee import (
    CharField,
    DateTimeField,
    FloatField,
    IntegerField,
    Model,
    SqliteDatabase,
)
from playhouse.sqlite_ext import JSONField

logger = logging.getLogger(__name__)

# Analytics database - separate from main frigate.db
analytics_db = SqliteDatabase(None)


class AnalyticsBaseModel(Model):
    """Base model for all analytics tables"""

    class Meta:
        database = analytics_db


class AnalyticsTicketStatus(AnalyticsBaseModel):
    """Pre-aggregated ticket counts by status"""

    status = CharField(primary_key=True, max_length=50)  # new, in_progress, etc.
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_ticket_status"


class AnalyticsViolationsByCamera(AnalyticsBaseModel):
    """Pre-aggregated violations count and percentage by camera"""

    camera = CharField(primary_key=True, max_length=20)
    violation_count = IntegerField(default=0)
    percentage = FloatField(default=0.0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_camera"


class AnalyticsViolationsByType(AnalyticsBaseModel):
    """Pre-aggregated violations by sub_label (violation type)"""

    sub_label = CharField(primary_key=True, max_length=100)
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_type"


class AnalyticsViolationsHourly(AnalyticsBaseModel):
    """Pre-aggregated violations by hour of day (0-23)"""

    hour = IntegerField(primary_key=True)  # 0-23
    count = IntegerField(default=0)
    percentage = FloatField(default=0.0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_hourly"


class AnalyticsViolationsByWeekday(AnalyticsBaseModel):
    """Pre-aggregated violations by weekday (0=Monday, 6=Sunday)"""

    weekday = IntegerField(primary_key=True)  # 0-6
    weekday_name = CharField(max_length=10)  # Monday, Tuesday, etc.
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_weekday"


class AnalyticsViolationsByMonth(AnalyticsBaseModel):
    """Pre-aggregated violations by month (1-12)"""

    month = IntegerField(primary_key=True)  # 1-12
    month_name = CharField(max_length=10)  # January, February, etc.
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_month"


class AnalyticsViolationsByQuarter(AnalyticsBaseModel):
    """Pre-aggregated violations by quarter"""

    quarter = IntegerField(primary_key=True)  # 1-4
    quarter_name = CharField(max_length=10)  # Q1, Q2, Q3, Q4
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_quarter"


class AnalyticsViolationsByYear(AnalyticsBaseModel):
    """Pre-aggregated violations by year"""

    year = IntegerField(primary_key=True)
    count = IntegerField(default=0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_violations_year"


class AnalyticsCameraFPS(AnalyticsBaseModel):
    """Pre-aggregated camera FPS metrics"""

    camera = CharField(primary_key=True, max_length=20)
    fps = FloatField(default=0.0)
    detection_fps = FloatField(default=0.0)
    process_fps = FloatField(default=0.0)
    skipped_fps = FloatField(default=0.0)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_camera_fps"


class AnalyticsCameraStatus(AnalyticsBaseModel):
    """Camera online/offline status for enabled cameras"""

    camera = CharField(primary_key=True, max_length=20)
    is_online = IntegerField(default=1)  # 1 = online, 0 = offline
    is_enabled = IntegerField(default=1)  # 1 = enabled, 0 = disabled
    last_seen = DateTimeField(null=True)
    last_updated = DateTimeField()

    class Meta:
        table_name = "analytics_camera_status"


# List of all analytics models
ANALYTICS_MODELS = [
    AnalyticsTicketStatus,
    AnalyticsViolationsByCamera,
    AnalyticsViolationsByType,
    AnalyticsViolationsHourly,
    AnalyticsViolationsByWeekday,
    AnalyticsViolationsByMonth,
    AnalyticsViolationsByQuarter,
    AnalyticsViolationsByYear,
    AnalyticsCameraFPS,
    AnalyticsCameraStatus,
]


def init_analytics_db(db_path: str):
    """
    Initialize the analytics database

    Args:
        db_path: Path to the analytics SQLite database file
    """
    logger.info(f"Initializing analytics database at {db_path}")
    analytics_db.init(db_path)
    analytics_db.connect()

    # Create tables if they don't exist
    analytics_db.create_tables(ANALYTICS_MODELS, safe=True)

    # Initialize hourly table with all hours (0-23)
    for hour in range(24):
        AnalyticsViolationsHourly.get_or_create(
            hour=hour,
            defaults={
                "count": 0,
                "percentage": 0.0,
                "last_updated": datetime.datetime.now(),
            },
        )

    # Initialize weekday table with all days (0-6)
    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    for weekday, name in enumerate(weekday_names):
        AnalyticsViolationsByWeekday.get_or_create(
            weekday=weekday,
            defaults={
                "weekday_name": name,
                "count": 0,
                "last_updated": datetime.datetime.now(),
            },
        )

    # Initialize month table with all months (1-12)
    month_names = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    for month, name in enumerate(month_names, start=1):
        AnalyticsViolationsByMonth.get_or_create(
            month=month,
            defaults={
                "month_name": name,
                "count": 0,
                "last_updated": datetime.datetime.now(),
            },
        )

    # Initialize quarter table with all quarters (1-4)
    for quarter in range(1, 5):
        AnalyticsViolationsByQuarter.get_or_create(
            quarter=quarter,
            defaults={
                "quarter_name": f"Q{quarter}",
                "count": 0,
                "last_updated": datetime.datetime.now(),
            },
        )

    # Initialize ticket statuses
    ticket_statuses = ["new", "in_progress", "solved", "closed", "fake"]
    for status in ticket_statuses:
        AnalyticsTicketStatus.get_or_create(
            status=status,
            defaults={"count": 0, "last_updated": datetime.datetime.now()},
        )

    logger.info("Analytics database initialized successfully")


def close_analytics_db():
    """Close the analytics database connection"""
    if not analytics_db.is_closed():
        analytics_db.close()
        logger.info("Analytics database connection closed")
