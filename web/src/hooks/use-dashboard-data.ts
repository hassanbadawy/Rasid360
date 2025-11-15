/**
 * Dashboard Data Hooks
 * Custom SWR hooks for fetching analytics data from dashboard API endpoints
 */

import useSWR from "swr";
import { baseUrl } from "@/api/baseUrl";

/**
 * Ticket status data type
 */
export type TicketStatusData = {
  status: string;
  count: number;
};

/**
 * Violations by camera data type
 */
export type ViolationsByCameraData = {
  camera: string;
  count: number;
  percentage: number;
};

/**
 * Violations by type data type
 */
export type ViolationsByTypeData = {
  sub_label: string;
  count: number;
};

/**
 * Hourly heatmap data type
 */
export type HourlyHeatmapData = {
  hour: number;
  count: number;
  percentage: number;
};

/**
 * Weekday data type
 */
export type WeekdayData = {
  weekday: number;
  weekday_name: string;
  count: number;
};

/**
 * Month data type
 */
export type MonthData = {
  month: number;
  month_name: string;
  count: number;
};

/**
 * Quarter data type
 */
export type QuarterData = {
  quarter: number;
  quarter_name: string;
  count: number;
};

/**
 * Year data type
 */
export type YearData = {
  year: number;
  count: number;
};

/**
 * Camera FPS data type
 */
export type CameraFPSData = {
  camera: string;
  fps: number;
  detection_fps: number;
  process_fps: number;
  skipped_fps: number;
};

/**
 * Offline camera data type
 */
export type OfflineCameraData = {
  camera: string;
  last_seen: number | null;
};

/**
 * Dashboard filter options
 */
export type DashboardFilters = {
  cameras?: string[];
  sub_labels?: string[];
  after?: number;
  before?: number;
};

/**
 * Build query string from filters
 */
function buildQueryString(filters?: DashboardFilters): string {
  if (!filters) return "";

  const params = new URLSearchParams();

  if (filters.cameras && filters.cameras.length > 0) {
    params.append("cameras", filters.cameras.join(","));
  }

  if (filters.sub_labels && filters.sub_labels.length > 0) {
    params.append("sub_labels", filters.sub_labels.join(","));
  }

  if (filters.after) {
    params.append("after", filters.after.toString());
  }

  if (filters.before) {
    params.append("before", filters.before.toString());
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}

/**
 * Fetch ticket status counts
 */
export function useTicketStatusData(filters?: DashboardFilters) {
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: TicketStatusData[];
  }>(`${baseUrl}api/dashboard/tickets/status${query}`, {
    refreshInterval: 300000, // 5 minutes
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by camera
 */
export function useViolationsByCameraData(filters?: DashboardFilters) {
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: ViolationsByCameraData[];
  }>(`${baseUrl}api/dashboard/violations/by-camera${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by type
 */
export function useViolationsByTypeData(
  filters?: DashboardFilters,
  limit?: number,
) {
  
  let query = buildQueryString(filters);

  if (limit) {
    query += (query ? "&" : "?") + `limit=${limit}`;
  }

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: ViolationsByTypeData[];
  }>(`${baseUrl}api/dashboard/violations/by-type${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch hourly heatmap
 */
export function useHourlyHeatmapData(filters?: DashboardFilters) {
  
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: HourlyHeatmapData[];
  }>(`${baseUrl}api/dashboard/violations/hourly-heatmap${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by weekday
 */
export function useViolationsByWeekdayData(filters?: DashboardFilters) {
  
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: WeekdayData[];
  }>(`${baseUrl}api/dashboard/violations/by-weekday${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by month
 */
export function useViolationsByMonthData(filters?: DashboardFilters) {
  
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: MonthData[];
  }>(`${baseUrl}api/dashboard/violations/by-month${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by quarter
 */
export function useViolationsByQuarterData(filters?: DashboardFilters) {
  
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: QuarterData[];
  }>(`${baseUrl}api/dashboard/violations/by-quarter${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch violations by year
 */
export function useViolationsByYearData(filters?: DashboardFilters) {
  
  const query = buildQueryString(filters);

  const { data, error, isLoading, mutate} = useSWR<{
    success: boolean;
    data: YearData[];
  }>(`${baseUrl}api/dashboard/violations/by-year${query}`, {
    refreshInterval: 300000,
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch camera FPS data
 */
export function useCameraFPSData() {
  

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: CameraFPSData[];
  }>(`${baseUrl}api/dashboard/camera/fps`, {
    refreshInterval: 30000, // 30 seconds for live data
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    error,
    isLoading,
    mutate,
  };
}

/**
 * Fetch offline cameras
 */
export function useOfflineCamerasData() {
  

  const { data, error, isLoading, mutate } = useSWR<{
    success: boolean;
    data: OfflineCameraData[];
    offline_count: number;
  }>(`${baseUrl}api/dashboard/camera/offline`, {
    refreshInterval: 30000, // 30 seconds for live data
    revalidateOnFocus: true,
  });

  return {
    data: data?.data || [],
    offlineCount: data?.offline_count || 0,
    error,
    isLoading,
    mutate,
  };
}
