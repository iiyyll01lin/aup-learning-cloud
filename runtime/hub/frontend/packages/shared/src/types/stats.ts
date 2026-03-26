// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

export interface DashboardOverview {
  total_users: number;
  active_sessions: number;
  total_usage_minutes: number;
  users_this_week: number;
}

export interface DailyUsage {
  date: string;
  minutes: number;
  sessions: number;
}

export interface ResourceDistribution {
  resource_type: string;
  minutes: number;
  sessions: number;
  users: number;
}

export interface TopUser {
  username: string;
  total_minutes: number;
  sessions: number;
}

export interface StatsUsageResponse {
  daily_usage: DailyUsage[];
}

export interface StatsDistributionResponse {
  by_resource: ResourceDistribution[];
  top_users: TopUser[];
}
