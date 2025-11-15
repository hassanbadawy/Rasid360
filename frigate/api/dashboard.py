"""
Dashboard API endpoints for analytics and metrics
Serves pre-aggregated data from analytics.db for fast dashboard performance
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

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
)
from frigate.api.auth import get_allowed_cameras_for_filter, require_camera_access
from frigate.models import Event
from peewee import fn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/tickets/status")
async def get_ticket_status_counts(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
    after: Optional[float] = Query(None, description="Timestamp after"),
    before: Optional[float] = Query(None, description="Timestamp before"),
):
    """
    Get ticket counts by status

    Returns counts for: new, in_progress, solved, closed, fake

    Supports filters: cameras, sub_labels, date range
    """
    try:
        # If filters are provided, query frigate.db directly with filters
        # Otherwise, use pre-aggregated data from analytics.db
        if cameras or sub_labels or after or before:
            # Parse filters
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            # Apply camera access control
            allowed_cameras = await get_allowed_cameras_for_filter(request)
            if camera_list:
                camera_list = [c for c in camera_list if c in allowed_cameras]
            else:
                camera_list = list(allowed_cameras)

            # Build query
            query = Event.select().where(Event.sub_label.is_null(False))

            if camera_list:
                query = query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                query = query.where(Event.sub_label.in_(sub_label_list))

            if after:
                query = query.where(Event.start_time >= after)

            if before:
                query = query.where(Event.start_time <= before)

            # Count by ticket status
            status_counts = {
                "new": 0,
                "in_progress": 0,
                "solved": 0,
                "closed": 0,
                "fake": 0,
            }

            for event in query:
                ticket_status = (
                    event.data.get("ticket_status", "new") if event.data else "new"
                )
                if ticket_status in status_counts:
                    status_counts[ticket_status] += 1
                else:
                    status_counts["new"] += 1

            result = [
                {"status": status, "count": count}
                for status, count in status_counts.items()
            ]

        else:
            # Use pre-aggregated data
            rows = AnalyticsTicketStatus.select().order_by(
                AnalyticsTicketStatus.status
            )
            result = [{"status": row.status, "count": row.count} for row in rows]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting ticket status counts: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-camera")
async def get_violations_by_camera(
    request: Request,
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
    after: Optional[float] = Query(None, description="Timestamp after"),
    before: Optional[float] = Query(None, description="Timestamp before"),
):
    """
    Get violation counts and percentages by camera

    Supports filters: sub_labels, date range
    """
    try:
        # If filters provided, query frigate.db
        if sub_labels or after or before:
            sub_label_list = sub_labels.split(",") if sub_labels else None

            # Build query
            query = Event.select(
                Event.camera, fn.COUNT(Event.id).alias("count")
            ).where(Event.sub_label.is_null(False))

            if sub_label_list:
                query = query.where(Event.sub_label.in_(sub_label_list))

            if after:
                query = query.where(Event.start_time >= after)

            if before:
                query = query.where(Event.start_time <= before)

            camera_counts = query.group_by(Event.camera)

            # Apply camera access control and calculate percentages
            allowed_cameras = await get_allowed_cameras_for_filter(request)

            filtered_counts = [
                row for row in camera_counts if row.camera in allowed_cameras
            ]

            total = sum(row.count for row in filtered_counts)

            result = [
                {
                    "camera": row.camera,
                    "count": row.count,
                    "percentage": round((row.count / total) * 100, 2) if total > 0 else 0,
                }
                for row in filtered_counts
            ]

        else:
            # Use pre-aggregated data with camera access control
            allowed_cameras = await get_allowed_cameras_for_filter(request)

            rows = (
                AnalyticsViolationsByCamera.select()
                .where(AnalyticsViolationsByCamera.camera.in_(allowed_cameras))
                .order_by(AnalyticsViolationsByCamera.violation_count.desc())
            )

            result = [
                {
                    "camera": row.camera,
                    "count": row.violation_count,
                    "percentage": row.percentage,
                }
                for row in rows
            ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by camera: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-type")
def get_violations_by_type(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    after: Optional[float] = Query(None, description="Timestamp after"),
    before: Optional[float] = Query(None, description="Timestamp before"),
    limit: Optional[int] = Query(None, description="Limit results (default: all)"),
):
    """
    Get violation counts by sub_label (violation type)
    Ordered by count descending

    Supports filters: cameras, date range
    """
    try:
        # If filters provided, query frigate.db
        if cameras or after or before:
            camera_list = cameras.split(",") if cameras else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query
            query = Event.select(
                Event.sub_label, fn.COUNT(Event.id).alias("count")
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                query = query.where(Event.camera.in_(camera_list))

            if after:
                query = query.where(Event.start_time >= after)

            if before:
                query = query.where(Event.start_time <= before)

            type_counts = query.group_by(Event.sub_label).order_by(
                fn.COUNT(Event.id).desc()
            )

            if limit:
                type_counts = type_counts.limit(limit)

            result = [
                {"sub_label": row.sub_label, "count": row.count}
                for row in type_counts
            ]

        else:
            # Use pre-aggregated data
            query = AnalyticsViolationsByType.select().order_by(
                AnalyticsViolationsByType.count.desc()
            )

            if limit:
                query = query.limit(limit)

            result = [{"sub_label": row.sub_label, "count": row.count} for row in query]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by type: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/hourly-heatmap")
def get_violations_hourly_heatmap(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
):
    """
    Get violation counts by hour of day (0-23)
    Always returns all 24 hours, even if count is 0

    Includes percentage of total violations
    """
    try:
        # If filters provided, query frigate.db
        if cameras or sub_labels:
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query
            hourly_query = Event.select(
                fn.strftime("%H", Event.start_time, "unixepoch")
                .cast("INTEGER")
                .alias("hour"),
                fn.COUNT(Event.id).alias("count"),
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                hourly_query = hourly_query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                hourly_query = hourly_query.where(Event.sub_label.in_(sub_label_list))

            hourly_counts = hourly_query.group_by(
                fn.strftime("%H", Event.start_time, "unixepoch")
            )

            # Convert to dict
            hour_dict = {row.hour: row.count for row in hourly_counts}
            total = sum(hour_dict.values())

            # Build result for all 24 hours
            result = [
                {
                    "hour": hour,
                    "count": hour_dict.get(hour, 0),
                    "percentage": (
                        round((hour_dict.get(hour, 0) / total) * 100, 2)
                        if total > 0
                        else 0
                    ),
                }
                for hour in range(24)
            ]

        else:
            # Use pre-aggregated data
            rows = AnalyticsViolationsHourly.select().order_by(
                AnalyticsViolationsHourly.hour
            )

            result = [
                {"hour": row.hour, "count": row.count, "percentage": row.percentage}
                for row in rows
            ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting hourly heatmap: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-weekday")
def get_violations_by_weekday(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
):
    """
    Get violation counts by weekday (0=Monday, 6=Sunday)
    Always returns all 7 days, even if count is 0
    """
    try:
        # If filters provided, query frigate.db
        if cameras or sub_labels:
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query
            weekday_query = Event.select(
                fn.strftime("%w", Event.start_time, "unixepoch")
                .cast("INTEGER")
                .alias("dow"),
                fn.COUNT(Event.id).alias("count"),
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                weekday_query = weekday_query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                weekday_query = weekday_query.where(Event.sub_label.in_(sub_label_list))

            weekday_counts = weekday_query.group_by(
                fn.strftime("%w", Event.start_time, "unixepoch")
            )

            # Convert SQLite weekday to ISO weekday
            weekday_dict = {}
            for row in weekday_counts:
                iso_weekday = (row.dow + 6) % 7
                weekday_dict[iso_weekday] = row.count

            # Weekday names
            weekday_names = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]

            result = [
                {
                    "weekday": weekday,
                    "weekday_name": weekday_names[weekday],
                    "count": weekday_dict.get(weekday, 0),
                }
                for weekday in range(7)
            ]

        else:
            # Use pre-aggregated data
            rows = AnalyticsViolationsByWeekday.select().order_by(
                AnalyticsViolationsByWeekday.weekday
            )

            result = [
                {
                    "weekday": row.weekday,
                    "weekday_name": row.weekday_name,
                    "count": row.count,
                }
                for row in rows
            ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by weekday: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-month")
def get_violations_by_month(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
):
    """
    Get violation counts by month (1-12)
    Always returns all 12 months, even if count is 0
    """
    try:
        # If filters provided, query frigate.db
        if cameras or sub_labels:
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query
            month_query = Event.select(
                fn.strftime("%m", Event.start_time, "unixepoch")
                .cast("INTEGER")
                .alias("month"),
                fn.COUNT(Event.id).alias("count"),
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                month_query = month_query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                month_query = month_query.where(Event.sub_label.in_(sub_label_list))

            month_counts = month_query.group_by(
                fn.strftime("%m", Event.start_time, "unixepoch")
            )

            month_dict = {row.month: row.count for row in month_counts}

            # Month names
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

            result = [
                {
                    "month": month,
                    "month_name": month_names[month - 1],
                    "count": month_dict.get(month, 0),
                }
                for month in range(1, 13)
            ]

        else:
            # Use pre-aggregated data
            rows = AnalyticsViolationsByMonth.select().order_by(
                AnalyticsViolationsByMonth.month
            )

            result = [
                {"month": row.month, "month_name": row.month_name, "count": row.count}
                for row in rows
            ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by month: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-quarter")
def get_violations_by_quarter(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
):
    """
    Get violation counts by quarter (Q1-Q4)
    Always returns all 4 quarters, even if count is 0
    """
    try:
        # If filters provided, query frigate.db
        if cameras or sub_labels:
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query (get by month first, then aggregate)
            month_query = Event.select(
                fn.strftime("%m", Event.start_time, "unixepoch")
                .cast("INTEGER")
                .alias("month"),
                fn.COUNT(Event.id).alias("count"),
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                month_query = month_query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                month_query = month_query.where(Event.sub_label.in_(sub_label_list))

            month_counts = month_query.group_by(
                fn.strftime("%m", Event.start_time, "unixepoch")
            )

            # Aggregate to quarters
            quarter_counts = {1: 0, 2: 0, 3: 0, 4: 0}
            for row in month_counts:
                quarter = ((row.month - 1) // 3) + 1
                quarter_counts[quarter] += row.count

            result = [
                {
                    "quarter": quarter,
                    "quarter_name": f"Q{quarter}",
                    "count": quarter_counts[quarter],
                }
                for quarter in range(1, 5)
            ]

        else:
            # Use pre-aggregated data
            rows = AnalyticsViolationsByQuarter.select().order_by(
                AnalyticsViolationsByQuarter.quarter
            )

            result = [
                {
                    "quarter": row.quarter,
                    "quarter_name": row.quarter_name,
                    "count": row.count,
                }
                for row in rows
            ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by quarter: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/violations/by-year")
def get_violations_by_year(
    request: Request,
    cameras: Optional[str] = Query(None, description="Comma-separated camera names"),
    sub_labels: Optional[str] = Query(
        None, description="Comma-separated violation types"
    ),
):
    """
    Get violation counts by year
    Returns all years that have violations
    """
    try:
        # If filters provided, query frigate.db
        if cameras or sub_labels:
            camera_list = cameras.split(",") if cameras else None
            sub_label_list = sub_labels.split(",") if sub_labels else None

            if camera_list:
                camera_list = get_allowed_cameras_for_filter(request, camera_list)

            # Build query
            year_query = Event.select(
                fn.strftime("%Y", Event.start_time, "unixepoch")
                .cast("INTEGER")
                .alias("year"),
                fn.COUNT(Event.id).alias("count"),
            ).where(Event.sub_label.is_null(False))

            if camera_list:
                year_query = year_query.where(Event.camera.in_(camera_list))

            if sub_label_list:
                year_query = year_query.where(Event.sub_label.in_(sub_label_list))

            year_counts = year_query.group_by(
                fn.strftime("%Y", Event.start_time, "unixepoch")
            ).order_by(fn.strftime("%Y", Event.start_time, "unixepoch"))

            result = [{"year": row.year, "count": row.count} for row in year_counts]

        else:
            # Use pre-aggregated data
            rows = AnalyticsViolationsByYear.select().order_by(
                AnalyticsViolationsByYear.year
            )

            result = [{"year": row.year, "count": row.count} for row in rows]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting violations by year: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/camera/fps")
def get_camera_fps(request: Request):
    """
    Get FPS metrics for all cameras
    Returns: fps, detection_fps, process_fps, skipped_fps per camera
    """
    try:
        # Apply camera access control
        allowed_cameras = get_allowed_cameras_for_filter(request, None)

        rows = (
            AnalyticsCameraFPS.select()
            .where(AnalyticsCameraFPS.camera.in_(allowed_cameras))
            .order_by(AnalyticsCameraFPS.camera)
        )

        result = [
            {
                "camera": row.camera,
                "fps": row.fps,
                "detection_fps": row.detection_fps,
                "process_fps": row.process_fps,
                "skipped_fps": row.skipped_fps,
            }
            for row in rows
        ]

        return JSONResponse(content={"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error getting camera FPS: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )


@router.get("/dashboard/camera/offline")
def get_offline_cameras(request: Request):
    """
    Get list of offline cameras (that are enabled)
    Returns camera names that are enabled but offline
    """
    try:
        # Apply camera access control
        allowed_cameras = get_allowed_cameras_for_filter(request, None)

        rows = (
            AnalyticsCameraStatus.select()
            .where(
                (AnalyticsCameraStatus.camera.in_(allowed_cameras))
                & (AnalyticsCameraStatus.is_enabled == 1)
                & (AnalyticsCameraStatus.is_online == 0)
            )
            .order_by(AnalyticsCameraStatus.camera)
        )

        result = [
            {
                "camera": row.camera,
                "last_seen": (
                    row.last_seen.timestamp() if row.last_seen else None
                ),
            }
            for row in rows
        ]

        return JSONResponse(
            content={
                "success": True,
                "data": result,
                "offline_count": len(result),
            }
        )

    except Exception as e:
        logger.error(f"Error getting offline cameras: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": str(e)}, status_code=500
        )
