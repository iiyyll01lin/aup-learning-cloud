// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { useState, useEffect, useCallback } from 'react';
import { Spinner, Alert } from 'react-bootstrap';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { NavBar } from '../components/NavBar';
import {
  getDashboardOverview,
  getUsageTimeSeries,
  getDistribution,
} from '@auplc/shared';
import type {
  DashboardOverview,
  DailyUsage,
  ResourceDistribution,
  TopUser,
} from '@auplc/shared';

const PIE_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444'];

const TIME_RANGES = [
  { label: '7 days', value: 7 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
];

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  color: string;
}

function StatCard({ title, value, icon, color }: StatCardProps) {
  return (
    <div className="tw:rounded-xl tw:p-5 tw:shadow-sm tw:border tw:border-gray-100 tw:bg-white tw:flex tw:items-center tw:gap-4">
      <div className={`tw:rounded-lg tw:p-3 ${color}`}>
        <i className={`bi ${icon} tw:text-white tw:text-xl`} />
      </div>
      <div>
        <p className="tw:text-sm tw:text-gray-500 tw:mb-0">{title}</p>
        <p className="tw:text-2xl tw:font-bold tw:text-gray-800 tw:mb-0">{value}</p>
      </div>
    </div>
  );
}

export function Dashboard() {
  const [days, setDays] = useState(30);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [dailyUsage, setDailyUsage] = useState<DailyUsage[]>([]);
  const [byResource, setByResource] = useState<ResourceDistribution[]>([]);
  const [topUsers, setTopUsers] = useState<TopUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [ov, usage, dist] = await Promise.all([
        getDashboardOverview(),
        getUsageTimeSeries(days),
        getDistribution(days),
      ]);
      setOverview(ov);
      setDailyUsage(usage.daily_usage);
      setByResource(dist.by_resource);
      setTopUsers(dist.top_users);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div>
      <NavBar />

      <div className="tw:flex tw:items-center tw:justify-between tw:mb-6">
        <h4 className="tw:text-gray-800 tw:font-semibold tw:mb-0">Usage Dashboard</h4>
        <div className="tw:flex tw:gap-1 tw:bg-gray-100 tw:rounded-lg tw:p-1">
          {TIME_RANGES.map(r => (
            <button
              key={r.value}
              onClick={() => setDays(r.value)}
              className={`tw:px-3 tw:py-1 tw:rounded-md tw:text-sm tw:font-medium tw:transition-all ${
                days === r.value
                  ? 'tw:bg-white tw:shadow-sm tw:text-indigo-600'
                  : 'tw:text-gray-500 tw:hover:text-gray-700'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="tw:flex tw:justify-center tw:py-20">
          <Spinner animation="border" variant="primary" />
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="tw:grid tw:grid-cols-2 tw:gap-4 tw:mb-6 md:tw:grid-cols-4">
            <StatCard
              title="Total Users"
              value={overview?.total_users ?? 0}
              icon="bi-people-fill"
              color="tw:bg-indigo-500"
            />
            <StatCard
              title="Active Sessions"
              value={overview?.active_sessions ?? 0}
              icon="bi-play-circle-fill"
              color="tw:bg-emerald-500"
            />
            <StatCard
              title="Total Usage"
              value={formatMinutes(overview?.total_usage_minutes ?? 0)}
              icon="bi-clock-history"
              color="tw:bg-violet-500"
            />
            <StatCard
              title="Active This Week"
              value={overview?.users_this_week ?? 0}
              icon="bi-activity"
              color="tw:bg-pink-500"
            />
          </div>

          {/* Charts row */}
          <div className="tw:grid tw:grid-cols-1 tw:gap-4 tw:mb-6 lg:tw:grid-cols-3">
            {/* Usage trend */}
            <div className="tw:bg-white tw:rounded-xl tw:shadow-sm tw:border tw:border-gray-100 tw:p-5 lg:tw:col-span-2">
              <h6 className="tw:text-gray-600 tw:font-semibold tw:mb-4">Daily Usage (minutes)</h6>
              {dailyUsage.length === 0 ? (
                <p className="tw:text-gray-400 tw:text-sm tw:text-center tw:py-10">No data for this period</p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={dailyUsage} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v) => [`${v} min`, 'Usage']} />
                    <Legend />
                    <Line type="monotone" dataKey="minutes" stroke="#6366f1" strokeWidth={2} dot={false} name="Minutes" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Resource distribution */}
            <div className="tw:bg-white tw:rounded-xl tw:shadow-sm tw:border tw:border-gray-100 tw:p-5">
              <h6 className="tw:text-gray-600 tw:font-semibold tw:mb-4">Resource Distribution</h6>
              {byResource.length === 0 ? (
                <p className="tw:text-gray-400 tw:text-sm tw:text-center tw:py-10">No data for this period</p>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={byResource}
                      dataKey="minutes"
                      nameKey="resource_type"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ resource_type, percent }) =>
                        `${resource_type} ${(percent * 100).toFixed(0)}%`
                      }
                      labelLine={false}
                    >
                      {byResource.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => [`${v} min`]} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Top users table */}
          <div className="tw:bg-white tw:rounded-xl tw:shadow-sm tw:border tw:border-gray-100 tw:p-5">
            <h6 className="tw:text-gray-600 tw:font-semibold tw:mb-4">Top Users</h6>
            {topUsers.length === 0 ? (
              <p className="tw:text-gray-400 tw:text-sm tw:text-center tw:py-6">No data for this period</p>
            ) : (
              <table className="table table-sm table-hover mb-0">
                <thead className="table-light">
                  <tr>
                    <th>#</th>
                    <th>Username</th>
                    <th>Total Usage</th>
                    <th>Sessions</th>
                    <th>Avg per Session</th>
                  </tr>
                </thead>
                <tbody>
                  {topUsers.map((u, i) => (
                    <tr key={u.username}>
                      <td className="tw:text-gray-400">{i + 1}</td>
                      <td><code>{u.username}</code></td>
                      <td>{formatMinutes(u.total_minutes)}</td>
                      <td>{u.sessions}</td>
                      <td>{formatMinutes(Math.round(u.total_minutes / u.sessions))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
