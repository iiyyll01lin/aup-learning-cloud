# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import json
from datetime import datetime, timedelta

from jupyterhub.apihandlers import APIHandler
from tornado import web

from core.database import session_scope
from core.quota.orm import UsageSession


def _require_admin(handler):
    if not handler.current_user.admin:
        handler.set_status(403)
        handler.set_header("Content-Type", "application/json")
        handler.finish(json.dumps({"error": "Admin access required"}))
        return False
    return True


class StatsOverviewHandler(APIHandler):
    """Summary stats for the dashboard overview cards."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self):
        from jupyterhub.orm import User

        week_ago = datetime.now() - timedelta(days=7)

        total_users = self.db.query(User).count()
        users_this_week = self.db.query(User).filter(User.last_activity >= week_ago).count()

        with session_scope() as session:
            active_sessions = (
                session.query(UsageSession).filter(UsageSession.status == "active").count()
            )
            total_minutes_row = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT COALESCE(SUM(duration_minutes), 0) FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') AND duration_minutes IS NOT NULL"
                )
            ).scalar()

        return {
            "total_users": total_users,
            "active_sessions": active_sessions,
            "total_usage_minutes": int(total_minutes_row or 0),
            "users_this_week": users_this_week,
        }


class StatsUsageHandler(APIHandler):
    """Usage time series for the trend line chart, supporting day/week granularity."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        granularity = self.get_argument("granularity", "day")
        if granularity not in ("day", "week"):
            granularity = "day"

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, days, granularity)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, days: int, granularity: str):
        import sqlalchemy as sa

        since = datetime.now() - timedelta(days=days)

        if granularity == "week":
            # SQLite: strftime('%Y-W%W', start_time) groups by ISO week
            group_expr = "strftime('%Y-W%W', start_time)"
        else:
            group_expr = "DATE(start_time)"

        with session_scope() as session:
            rows = session.execute(
                sa.text(
                    f"SELECT {group_expr} as period, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions, "
                    "COUNT(DISTINCT username) as users "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    f"GROUP BY {group_expr} "
                    "ORDER BY period ASC"
                ),
                {"since": since},
            ).fetchall()

        return {
            "daily_usage": [
                {"date": str(row[0]), "minutes": int(row[1]), "sessions": int(row[2]), "users": int(row[3])}
                for row in rows
            ]
        }


class StatsDistributionHandler(APIHandler):
    """Resource distribution and top users for pie chart and leaderboard."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, days)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, days: int):
        import sqlalchemy as sa

        since = datetime.now() - timedelta(days=days)

        with session_scope() as session:
            resource_rows = session.execute(
                sa.text(
                    "SELECT resource_type, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions, "
                    "COUNT(DISTINCT username) as users, "
                    "COALESCE(AVG(duration_minutes), 0) as avg_minutes "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY resource_type "
                    "ORDER BY minutes DESC"
                ),
                {"since": since},
            ).fetchall()

            top_user_rows = session.execute(
                sa.text(
                    "SELECT username, "
                    "COALESCE(SUM(duration_minutes), 0) as total_minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY username "
                    "ORDER BY total_minutes DESC "
                    "LIMIT 10"
                ),
                {"since": since},
            ).fetchall()

        return {
            "by_resource": [
                {
                    "resource_type": row[0],
                    "minutes": int(row[1]),
                    "sessions": int(row[2]),
                    "users": int(row[3]),
                    "avg_minutes": round(float(row[4]), 1),
                }
                for row in resource_rows
            ],
            "top_users": [
                {
                    "username": row[0],
                    "total_minutes": int(row[1]),
                    "sessions": int(row[2]),
                }
                for row in top_user_rows
            ],
        }


class StatsUserHandler(APIHandler):
    """Per-user usage detail: time series + resource breakdown + recent sessions."""

    @web.authenticated
    async def get(self, username: str):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        granularity = self.get_argument("granularity", "day")
        if granularity not in ("day", "week"):
            granularity = "day"

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, username, days, granularity)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, username: str, days: int, granularity: str):
        import sqlalchemy as sa

        since = datetime.now() - timedelta(days=days)

        if granularity == "week":
            group_expr = "strftime('%Y-W%W', start_time)"
        else:
            group_expr = "DATE(start_time)"

        with session_scope() as session:
            # Time series for this user
            usage_rows = session.execute(
                sa.text(
                    f"SELECT {group_expr} as period, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    f"GROUP BY {group_expr} "
                    "ORDER BY period ASC"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Resource breakdown for this user
            resource_rows = session.execute(
                sa.text(
                    "SELECT resource_type, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY resource_type "
                    "ORDER BY minutes DESC"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Recent sessions (last 20)
            session_rows = session.execute(
                sa.text(
                    "SELECT resource_type, start_time, end_time, duration_minutes, status "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND start_time >= :since "
                    "ORDER BY start_time DESC "
                    "LIMIT 20"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Totals
            totals_row = session.execute(
                sa.text(
                    "SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*) "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since"
                ),
                {"username": username, "since": since},
            ).fetchone()

        return {
            "username": username,
            "total_minutes": int(totals_row[0] or 0),
            "total_sessions": int(totals_row[1] or 0),
            "usage": [
                {"date": str(r[0]), "minutes": int(r[1]), "sessions": int(r[2])}
                for r in usage_rows
            ],
            "by_resource": [
                {"resource_type": r[0], "minutes": int(r[1]), "sessions": int(r[2])}
                for r in resource_rows
            ],
            "recent_sessions": [
                {
                    "resource_type": r[0],
                    "start_time": str(r[1]),
                    "end_time": str(r[2]) if r[2] else None,
                    "duration_minutes": int(r[3]) if r[3] is not None else None,
                    "status": r[4],
                }
                for r in session_rows
            ],
        }


IDLE_WARN_MINUTES = 120  # sessions longer than this are flagged as potentially idle


def _active_sessions_data() -> dict:
    import sqlalchemy as sa

    cutoff = datetime.now() - timedelta(minutes=30)

    with session_scope() as session:
        active_rows = session.execute(
            sa.text(
                "SELECT q.username, q.resource_type, q.start_time "
                "FROM quota_usage_sessions q "
                "JOIN spawners s ON s.server_id IS NOT NULL "
                "JOIN users u ON u.id = s.user_id AND LOWER(u.name) = LOWER(q.username) "
                "WHERE q.status = 'active' "
                "ORDER BY q.start_time ASC"
            )
        ).fetchall()

        pending_rows = session.execute(
            sa.text(
                "SELECT u.name, s.started "
                "FROM spawners s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.server_id IS NULL AND s.started IS NOT NULL AND s.started > :cutoff "
                "ORDER BY s.started ASC"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    now = datetime.now()
    return {
        "active_sessions": [
            {
                "username": r[0],
                "resource_type": r[1],
                "start_time": str(r[2]),
                "elapsed_minutes": int(
                    (now - datetime.fromisoformat(str(r[2]))).total_seconds() / 60
                ),
                "idle_warning": int(
                    (now - datetime.fromisoformat(str(r[2]))).total_seconds() / 60
                ) >= IDLE_WARN_MINUTES,
            }
            for r in active_rows
        ],
        "pending_spawns": [
            {
                "username": r[0],
                "started": str(r[1]),
                "waiting_minutes": int(
                    (now - datetime.fromisoformat(str(r[1]))).total_seconds() / 60
                ),
            }
            for r in pending_rows
        ],
    }


class StatsActiveSSEHandler(APIHandler):
    """SSE stream of currently active sessions, pushed every 5 seconds."""

    def check_xsrf_cookie(self):
        # EventSource cannot send custom headers, so XSRF is skipped for this read-only GET
        pass

    @web.authenticated
    async def get(self):
        import asyncio

        assert self.current_user is not None
        if not _require_admin(self):
            return

        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")
        self.set_header("Connection", "keep-alive")

        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, _active_sessions_data)
                self.write(f"data: {json.dumps(data)}\n\n")
                await self.flush()
                await asyncio.sleep(5)
        except Exception:
            pass
