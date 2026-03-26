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
    """Daily usage time series for the trend line chart."""

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
            rows = session.execute(
                sa.text(
                    "SELECT DATE(start_time) as day, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY DATE(start_time) "
                    "ORDER BY day ASC"
                ),
                {"since": since},
            ).fetchall()

        return {
            "daily_usage": [
                {"date": str(row[0]), "minutes": int(row[1]), "sessions": int(row[2])}
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
                    "COUNT(DISTINCT username) as users "
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
