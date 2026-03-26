// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

import { adminApiRequest } from "./client.js";
import type {
  DashboardOverview,
  StatsDistributionResponse,
  StatsUsageResponse,
} from "../types/stats.js";

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return adminApiRequest<DashboardOverview>("/stats/overview");
}

export async function getUsageTimeSeries(days = 30): Promise<StatsUsageResponse> {
  return adminApiRequest<StatsUsageResponse>(`/stats/usage?days=${days}`);
}

export async function getDistribution(days = 30): Promise<StatsDistributionResponse> {
  return adminApiRequest<StatsDistributionResponse>(`/stats/distribution?days=${days}`);
}
