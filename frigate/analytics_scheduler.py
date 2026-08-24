"""
Analytics Scheduler - Periodically aggregates data from frigate.db to analytics.db
Runs every 5 minutes to update dashboard metrics with minimal performance impact
"""

import datetime
import logging
import threading
import time
from peewee import fn
from playhouse.sqliteq import SqliteQueueDatabase

from frigate.analytics_db import (
    AnalyticsCameraFPS,
    AnalyticsCameraStatus,
    AnalyticsTicketStatus,
    AnalyticsViolationsByCamera,
    AnalyticsViolationsByMonth,
    AnalyticsViolationsByQuarter,
    AnalyticsViolationsByType,
    AnalyticsViolationsByWeekday,
    AnalyticsViolationsByYear,
    AnalyticsViolationsHourly,
    analytics_db,
)
from frigate.models import Event
from frigate.violations import violation_events_clause

logger = logging.getLogger(__name__)


class AnalyticsScheduler:
    """
    Scheduler that aggregates event data into analytics tables
    Runs in background thread with configurable interval
    """

    def __init__(self, interval_seconds=300, frigate_db=None):  # Default: 5 minutes
        """
        Initialize the analytics scheduler

        Args:
            interval_seconds: How often to run aggregation (default 300 = 5 minutes)
            frigate_db: The main Frigate database connection
        """
        self.interval_seconds = interval_seconds
        self.frigate_db = frigate_db
        self.running = False
        self.thread = None
        logger.info(
            f"Analytics scheduler initialized (interval: {interval_seconds}s)"
        )

    def start(self):
        """Start the analytics scheduler in a background thread"""
        if self.running:
            logger.warning("Analytics scheduler already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Analytics scheduler started")

        # Run initial aggregation immediately
        self.aggregate_all()

    def stop(self):
        """Stop the analytics scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Analytics scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop - runs aggregation at specified intervals"""
        while self.running:
            try:
                time.sleep(self.interval_seconds)
                if self.running:  # Check again after sleep
                    self.aggregate_all()
            except Exception as e:
                logger.error(f"Error in analytics scheduler loop: {e}", exc_info=True)

    def aggregate_all(self):
        """
        Run all aggregation queries and update analytics tables
        This is the main entry point for data aggregation
        """
        start_time = time.time()
        logger.info("Starting analytics aggregation...")

        try:
            self.aggregate_ticket_status()
            self.aggregate_violations_by_camera()
            self.aggregate_violations_by_type()
            self.aggregate_violations_hourly()
            self.aggregate_violations_by_weekday()
            self.aggregate_violations_by_month()
            self.aggregate_violations_by_quarter()
            self.aggregate_violations_by_year()
            # Note: FPS and camera status will be updated from live stats, not here

            elapsed = time.time() - start_time
            logger.info(f"Analytics aggregation completed in {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"Error during analytics aggregation: {e}", exc_info=True)

    def aggregate_ticket_status(self):
        """Aggregate ticket counts by status"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Count by ticket_status in SQL rather than materializing every
            # violation event -- this runs over the full history each pass.
            status_field = Event.data["ticket_status"].cast("text")
            rows = list(
                Event.select(
                    status_field.alias("ticket_status"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(status_field)
            )

            status_counts = {
                "new": 0,
                "in_progress": 0,
                "solved": 0,
                "closed": 0,
                "fake": 0,
            }

            for row in rows:
                # Events with no ticket yet, and any unrecognized status, count as new.
                status = row.ticket_status if row.ticket_status in status_counts else "new"
                status_counts[status] += row.count

            # Update analytics table
            for status, count in status_counts.items():
                AnalyticsTicketStatus.update(
                    count=count, last_updated=now
                ).where(AnalyticsTicketStatus.status == status).execute()

            logger.debug(f"Updated ticket status counts: {status_counts}")

        except Exception as e:
            logger.error(f"Error aggregating ticket status: {e}", exc_info=True)

    def aggregate_violations_by_camera(self):
        """Aggregate violation counts and percentages by camera"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violation counts per camera
            camera_counts = list(
                Event.select(Event.camera, fn.COUNT(Event.id).alias("count"))
                .where(violation_events_clause())
                .group_by(Event.camera)
            )

            # Calculate total for percentages
            total_violations = sum(row.count for row in camera_counts)

            # Clear existing data
            AnalyticsViolationsByCamera.delete().execute()

            # Insert new data
            if total_violations > 0:
                for row in camera_counts:
                    percentage = (row.count / total_violations) * 100
                    AnalyticsViolationsByCamera.create(
                        camera=row.camera,
                        violation_count=row.count,
                        percentage=round(percentage, 2),
                        last_updated=now,
                    )

            logger.debug(
                f"Updated violations by camera ({len(camera_counts)} cameras)"
            )

        except Exception as e:
            logger.error(f"Error aggregating violations by camera: {e}", exc_info=True)

    def aggregate_violations_by_type(self):
        """Aggregate violation counts by sub_label (violation type)"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violation counts per type
            type_counts = list(
                Event.select(Event.sub_label, fn.COUNT(Event.id).alias("count"))
                .where(violation_events_clause())
                .group_by(Event.sub_label)
                .order_by(fn.COUNT(Event.id).desc())
            )

            # Clear existing data
            AnalyticsViolationsByType.delete().execute()

            # Insert new data
            for row in type_counts:
                AnalyticsViolationsByType.create(
                    sub_label=row.sub_label, count=row.count, last_updated=now
                )

            logger.debug(
                f"Updated violations by type ({len(type_counts)} types)"
            )

        except Exception as e:
            logger.error(f"Error aggregating violations by type: {e}", exc_info=True)

    def aggregate_violations_hourly(self):
        """Aggregate violations by hour of day (0-23)"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violations grouped by hour
            # Extract hour from start_time (stored as datetime/timestamp)
            hourly_counts = list(
                Event.select(
                    fn.strftime("%H", Event.start_time, "unixepoch").cast("INTEGER").alias("hour"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(fn.strftime("%H", Event.start_time, "unixepoch"))
            )

            # Convert to dict for easy lookup
            hour_dict = {row.hour: row.count for row in hourly_counts}

            # Calculate total for percentages
            total_violations = sum(hour_dict.values())

            # Update all hours (0-23)
            for hour in range(24):
                count = hour_dict.get(hour, 0)
                percentage = (
                    (count / total_violations) * 100 if total_violations > 0 else 0
                )

                AnalyticsViolationsHourly.update(
                    count=count, percentage=round(percentage, 2), last_updated=now
                ).where(AnalyticsViolationsHourly.hour == hour).execute()

            logger.debug(f"Updated hourly violations (total: {total_violations})")

        except Exception as e:
            logger.error(f"Error aggregating hourly violations: {e}", exc_info=True)

    def aggregate_violations_by_weekday(self):
        """Aggregate violations by weekday (0=Monday, 6=Sunday)"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violations grouped by weekday
            # SQLite strftime '%w' returns 0=Sunday, 6=Saturday
            # Convert to 0=Monday, 6=Sunday by adjusting
            weekday_counts = list(
                Event.select(
                    fn.strftime("%w", Event.start_time, "unixepoch").cast("INTEGER").alias("dow"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(fn.strftime("%w", Event.start_time, "unixepoch"))
            )

            # Convert SQLite weekday (0=Sun) to ISO weekday (0=Mon)
            # SQLite: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
            # ISO: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
            weekday_dict = {}
            for row in weekday_counts:
                iso_weekday = (row.dow + 6) % 7  # Convert SQLite to ISO
                weekday_dict[iso_weekday] = row.count

            # Update all weekdays (0-6)
            for weekday in range(7):
                count = weekday_dict.get(weekday, 0)
                AnalyticsViolationsByWeekday.update(
                    count=count, last_updated=now
                ).where(AnalyticsViolationsByWeekday.weekday == weekday).execute()

            logger.debug(f"Updated weekday violations")

        except Exception as e:
            logger.error(f"Error aggregating weekday violations: {e}", exc_info=True)

    def aggregate_violations_by_month(self):
        """Aggregate violations by month (1-12)"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violations grouped by month
            month_counts = list(
                Event.select(
                    fn.strftime("%m", Event.start_time, "unixepoch").cast("INTEGER").alias("month"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(fn.strftime("%m", Event.start_time, "unixepoch"))
            )

            # Convert to dict
            month_dict = {row.month: row.count for row in month_counts}

            # Update all months (1-12)
            for month in range(1, 13):
                count = month_dict.get(month, 0)
                AnalyticsViolationsByMonth.update(
                    count=count, last_updated=now
                ).where(AnalyticsViolationsByMonth.month == month).execute()

            logger.debug(f"Updated monthly violations")

        except Exception as e:
            logger.error(f"Error aggregating monthly violations: {e}", exc_info=True)

    def aggregate_violations_by_quarter(self):
        """Aggregate violations by quarter (Q1-Q4)"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violations grouped by month, then aggregate to quarters
            month_counts = list(
                Event.select(
                    fn.strftime("%m", Event.start_time, "unixepoch").cast("INTEGER").alias("month"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(fn.strftime("%m", Event.start_time, "unixepoch"))
            )

            # Aggregate months to quarters
            # Q1: Jan(1), Feb(2), Mar(3) | Q2: Apr(4), May(5), Jun(6)
            # Q3: Jul(7), Aug(8), Sep(9) | Q4: Oct(10), Nov(11), Dec(12)
            quarter_counts = {1: 0, 2: 0, 3: 0, 4: 0}

            for row in month_counts:
                quarter = ((row.month - 1) // 3) + 1
                quarter_counts[quarter] += row.count

            # Update all quarters (1-4)
            for quarter in range(1, 5):
                count = quarter_counts.get(quarter, 0)
                AnalyticsViolationsByQuarter.update(
                    count=count, last_updated=now
                ).where(AnalyticsViolationsByQuarter.quarter == quarter).execute()

            logger.debug(f"Updated quarterly violations")

        except Exception as e:
            logger.error(f"Error aggregating quarterly violations: {e}", exc_info=True)

    def aggregate_violations_by_year(self):
        """Aggregate violations by year"""
        try:
            now = datetime.datetime.now()

            # Bind Event to frigate database if available
            if self.frigate_db and not Event._meta.database.is_closed():
                Event._meta.set_database(self.frigate_db)

            # Get violations grouped by year
            year_counts = list(
                Event.select(
                    fn.strftime("%Y", Event.start_time, "unixepoch").cast("INTEGER").alias("year"),
                    fn.COUNT(Event.id).alias("count"),
                )
                .where(violation_events_clause())
                .group_by(fn.strftime("%Y", Event.start_time, "unixepoch"))
            )

            # Clear existing data
            AnalyticsViolationsByYear.delete().execute()

            # Insert new data
            for row in year_counts:
                AnalyticsViolationsByYear.create(
                    year=row.year, count=row.count, last_updated=now
                )

            logger.debug(f"Updated yearly violations ({len(year_counts)} years)")

        except Exception as e:
            logger.error(f"Error aggregating yearly violations: {e}", exc_info=True)

    def update_camera_fps(self, camera_name: str, fps_data: dict):
        """
        Update camera FPS metrics (called from live stats)

        Args:
            camera_name: Name of the camera
            fps_data: Dict with fps, detection_fps, process_fps, skipped_fps
        """
        try:
            now = datetime.datetime.now()

            AnalyticsCameraFPS.insert(
                camera=camera_name,
                fps=fps_data.get("fps", 0.0),
                detection_fps=fps_data.get("detection_fps", 0.0),
                process_fps=fps_data.get("process_fps", 0.0),
                skipped_fps=fps_data.get("skipped_fps", 0.0),
                last_updated=now,
            ).on_conflict(
                conflict_target=[AnalyticsCameraFPS.camera],
                update={
                    AnalyticsCameraFPS.fps: fps_data.get("fps", 0.0),
                    AnalyticsCameraFPS.detection_fps: fps_data.get(
                        "detection_fps", 0.0
                    ),
                    AnalyticsCameraFPS.process_fps: fps_data.get("process_fps", 0.0),
                    AnalyticsCameraFPS.skipped_fps: fps_data.get("skipped_fps", 0.0),
                    AnalyticsCameraFPS.last_updated: now,
                },
            ).execute()

        except Exception as e:
            logger.error(f"Error updating camera FPS for {camera_name}: {e}")

    def update_camera_status(
        self, camera_name: str, is_online: bool, is_enabled: bool
    ):
        """
        Update camera online/offline status (called from config/stats)

        Args:
            camera_name: Name of the camera
            is_online: Whether the camera is currently online
            is_enabled: Whether the camera is enabled in config
        """
        try:
            now = datetime.datetime.now()

            AnalyticsCameraStatus.insert(
                camera=camera_name,
                is_online=1 if is_online else 0,
                is_enabled=1 if is_enabled else 0,
                last_seen=now if is_online else None,
                last_updated=now,
            ).on_conflict(
                conflict_target=[AnalyticsCameraStatus.camera],
                update={
                    AnalyticsCameraStatus.is_online: 1 if is_online else 0,
                    AnalyticsCameraStatus.is_enabled: 1 if is_enabled else 0,
                    AnalyticsCameraStatus.last_seen: (
                        now if is_online else AnalyticsCameraStatus.last_seen
                    ),
                    AnalyticsCameraStatus.last_updated: now,
                },
            ).execute()

        except Exception as e:
            logger.error(f"Error updating camera status for {camera_name}: {e}")


# Global scheduler instance
_analytics_scheduler = None


def get_analytics_scheduler() -> AnalyticsScheduler:
    """Get the global analytics scheduler instance"""
    global _analytics_scheduler
    return _analytics_scheduler


def init_analytics_scheduler(interval_seconds=300, frigate_db=None):
    """
    Initialize and start the global analytics scheduler

    Args:
        interval_seconds: How often to run aggregation (default 300 = 5 minutes)
        frigate_db: The main Frigate database connection
    """
    global _analytics_scheduler

    if _analytics_scheduler is not None:
        logger.warning("Analytics scheduler already initialized")
        return _analytics_scheduler

    _analytics_scheduler = AnalyticsScheduler(interval_seconds=interval_seconds, frigate_db=frigate_db)
    _analytics_scheduler.start()

    return _analytics_scheduler


def stop_analytics_scheduler():
    """Stop the global analytics scheduler"""
    global _analytics_scheduler

    if _analytics_scheduler:
        _analytics_scheduler.stop()
        _analytics_scheduler = None
