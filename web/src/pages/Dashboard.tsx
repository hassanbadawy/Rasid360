import { useCallback, useMemo } from "react";
import ReactECharts from "echarts-for-react";
import useSWR from "swr";
import { FrigateConfig } from "@/types/frigateConfig";
import {
  DashboardFilters,
  useHourlyHeatmapData,
  useOfflineCamerasData,
  useTicketStatusData,
  useViolationsByCameraData,
  useViolationsByMonthData,
  useViolationsByQuarterData,
  useViolationsByTypeData,
  useViolationsByWeekdayData,
  useViolationsByYearData,
} from "@/hooks/use-dashboard-data";
import { LuTriangleAlert, LuRefreshCw } from "react-icons/lu";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTheme } from "@/context/theme-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Dashboard() {
  const { data: config } = useSWR<FrigateConfig>("config", {
    revalidateOnFocus: false,
  });
  const { theme } = useTheme();
  const filters: DashboardFilters = {};

  // Fetch all dashboard data
  const ticketStatus = useTicketStatusData(filters);
  const violationsByCamera = useViolationsByCameraData(filters);
  const violationsByType = useViolationsByTypeData(filters, 10);
  const hourlyHeatmap = useHourlyHeatmapData(filters);
  const weekdayData = useViolationsByWeekdayData(filters);
  const monthData = useViolationsByMonthData(filters);
  const quarterData = useViolationsByQuarterData(filters);
  const yearData = useViolationsByYearData(filters);
  const offlineCameras = useOfflineCamerasData();

  const isDark = theme === "dark";

  // ECharts theme colors
  const colors = {
    primary: isDark ? "#60a5fa" : "#3b82f6",
    success: isDark ? "#4ade80" : "#22c55e",
    warning: isDark ? "#facc15" : "#eab308",
    danger: isDark ? "#f87171" : "#ef4444",
    secondary: isDark ? "#9ca3af" : "#6b7280",
    background: isDark ? "#1f2937" : "#ffffff",
    text: isDark ? "#f3f4f6" : "#111827",
  };

  // Ticket status card colors
  const statusColors: Record<string, string> = {
    new: "#3b82f6",
    in_progress: "#eab308",
    solved: "#22c55e",
    closed: "#6b7280",
    fake: "#ef4444",
  };

  // Refresh all data
  const refreshAll = useCallback(() => {
    ticketStatus.mutate();
    violationsByCamera.mutate();
    violationsByType.mutate();
    hourlyHeatmap.mutate();
    weekdayData.mutate();
    monthData.mutate();
    quarterData.mutate();
    yearData.mutate();
    offlineCameras.mutate();
  }, [
    ticketStatus,
    violationsByCamera,
    violationsByType,
    hourlyHeatmap,
    weekdayData,
    monthData,
    quarterData,
    yearData,
    offlineCameras,
  ]);

  // Camera filter handler (simplified for now)
  // TODO: Add camera filter component once groups are available
  // const handleCameraFilter = useCallback((cameras: string[]) => {
  //   setFilters((prev) => ({ ...prev, cameras: cameras.length > 0 ? cameras : undefined }));
  // }, []);

  // Violations by camera pie chart
  const camerasPieOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} violations ({d}%)",
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
      textStyle: { color: colors.text },
      formatter: (name: string) => {
        const item = violationsByCamera.data.find((d) => d.camera === name);
        return `${name}: ${item?.count || 0}`;
      },
    },
    series: [
      {
        name: "Violations",
        type: "pie",
        radius: ["40%", "70%"],
        center: ["40%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: colors.background,
          borderWidth: 2,
        },
        label: {
          show: true,
          position: "outside",
          formatter: "{b}\n{d}%",
          color: colors.text,
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: "bold",
          },
        },
        labelLine: {
          show: true,
          lineStyle: { color: colors.text },
        },
        data: violationsByCamera.data.length > 0
          ? violationsByCamera.data.map((item) => ({
              value: item.count,
              name: item.camera,
            }))
          : [{ value: 1, name: "No Data", itemStyle: { color: colors.secondary } }],
      },
    ],
  }), [violationsByCamera.data, colors]);

  // Violations by type bar chart (Top Incidences)
  const typeBarOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: "{b}: {c} incidents",
    },
    grid: {
      left: "30%",  // Adjusted for better alignment
      right: "15%",
      bottom: "10%",
      top: "10%",
      containLabel: true,
    },
    xAxis: {
      type: "value",
      axisLabel: { color: colors.text },
      splitLine: { lineStyle: { color: isDark ? "#374151" : "#e5e7eb" } },
    },
    yAxis: {
      type: "category",
      data: violationsByType.data.length > 0
        ? violationsByType.data.map((item) => item.sub_label).reverse()
        : ["No Data"],
      axisLabel: {
        color: colors.text,
        fontSize: 12,
        overflow: "truncate",
        width: 150,
        formatter: (value: string) => {
          // Truncate long labels and add ellipsis
          return value.length > 20 ? value.substring(0, 20) + "..." : value;
        },
      },
      axisTick: { show: false },
    },
    series: [
      {
        name: "Incidents",
        type: "bar",
        data: violationsByType.data.length > 0
          ? violationsByType.data.map((item) => item.count).reverse()
          : [0],
        itemStyle: {
          color: colors.primary,
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: "right",
          color: colors.text,
          fontSize: 11,
        },
      },
    ],
  }), [violationsByType.data, colors, isDark]);

  // Hourly heatmap
  const heatmapOption = useMemo(() => {
    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    const data = hourlyHeatmap.data.map((item) => [item.hour, 0, item.count]);

    return {
      backgroundColor: "transparent",
      tooltip: {
        position: "top",
        formatter: (params: any) => {
          const hour = params.data[0];
          const count = params.data[2];
          const percentage = hourlyHeatmap.data[hour]?.percentage || 0;
          return `${hour}:00<br/>Count: ${count}<br/>Percentage: ${percentage.toFixed(2)}%`;
        },
      },
      grid: {
        height: "50%",
        top: "10%",
      },
      xAxis: {
        type: "category",
        data: hours,
        splitArea: { show: true },
        axisLabel: { color: colors.text },
      },
      yAxis: {
        type: "category",
        data: ["Violations"],
        splitArea: { show: true },
        axisLabel: { color: colors.text },
      },
      visualMap: {
        min: 0,
        max: Math.max(...hourlyHeatmap.data.map((d) => d.count), 1),
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: "0%",
        inRange: {
          color: ["#e0f2fe", "#0ea5e9", "#0369a1"],
        },
        textStyle: { color: colors.text },
      },
      series: [
        {
          name: "Violations",
          type: "heatmap",
          data: data,
          label: {
            show: true,
            color: colors.text,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.5)",
            },
          },
        },
      ],
    };
  }, [hourlyHeatmap.data, colors]);

  // Weekday bar chart
  const weekdayOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    grid: {
      left: "10%",
      right: "10%",
      bottom: "15%",
      top: "10%",
    },
    xAxis: {
      type: "category",
      data: weekdayData.data.map((item) => item.weekday_name.substring(0, 3)),
      axisLabel: { color: colors.text },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: colors.text },
      splitLine: { lineStyle: { color: isDark ? "#374151" : "#e5e7eb" } },
    },
    series: [
      {
        data: weekdayData.data.map((item) => item.count),
        type: "bar",
        itemStyle: {
          color: colors.primary,
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  }), [weekdayData.data, colors, isDark]);

  // Month bar chart
  const monthOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    grid: {
      left: "10%",
      right: "10%",
      bottom: "15%",
      top: "10%",
    },
    xAxis: {
      type: "category",
      data: monthData.data.map((item) => item.month_name.substring(0, 3)),
      axisLabel: { color: colors.text, rotate: 45 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: colors.text },
      splitLine: { lineStyle: { color: isDark ? "#374151" : "#e5e7eb" } },
    },
    series: [
      {
        data: monthData.data.map((item) => item.count),
        type: "bar",
        itemStyle: {
          color: colors.success,
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  }), [monthData.data, colors, isDark]);

  // Quarter bar chart
  const quarterOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    grid: {
      left: "10%",
      right: "10%",
      bottom: "15%",
      top: "10%",
    },
    xAxis: {
      type: "category",
      data: quarterData.data.map((item) => item.quarter_name),
      axisLabel: { color: colors.text },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: colors.text },
      splitLine: { lineStyle: { color: isDark ? "#374151" : "#e5e7eb" } },
    },
    series: [
      {
        data: quarterData.data.map((item) => item.count),
        type: "bar",
        itemStyle: {
          color: colors.warning,
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  }), [quarterData.data, colors, isDark]);

  // Year line chart
  const yearOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
    },
    grid: {
      left: "10%",
      right: "10%",
      bottom: "15%",
      top: "10%",
    },
    xAxis: {
      type: "category",
      data: yearData.data.map((item) => item.year.toString()),
      axisLabel: { color: colors.text },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: colors.text },
      splitLine: { lineStyle: { color: isDark ? "#374151" : "#e5e7eb" } },
    },
    series: [
      {
        data: yearData.data.map((item) => item.count),
        type: "line",
        smooth: true,
        itemStyle: { color: colors.danger },
        lineStyle: { width: 3 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${colors.danger}80` },
              { offset: 1, color: `${colors.danger}10` },
            ],
          },
        },
      },
    ],
  }), [yearData.data, colors, isDark]);

  if (!config) {
    return <div className="p-4">Loading...</div>;
  }

  return (
    <div className="flex size-full flex-col gap-4 overflow-y-auto p-4">
      {/* Header with filters and refresh */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-2">
          <Button onClick={refreshAll} size="sm" variant="outline">
            <LuRefreshCw className="mr-2 size-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Offline cameras alert */}
      {offlineCameras.offlineCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-red-500/10 p-4 text-red-500">
          <LuTriangleAlert className="size-5" />
          <span className="font-medium">
            {offlineCameras.offlineCount} camera(s) offline:{" "}
            {offlineCameras.data.map((cam) => cam.camera).join(", ")}
          </span>
        </div>
      )}

      {/* Ticket status cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {ticketStatus.isLoading ? (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          ticketStatus.data.map((status) => (
            <Card key={status.status}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm capitalize text-muted-foreground">
                  {status.status.replace("_", " ")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold" style={{ color: statusColors[status.status] }}>
                  {status.count}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Row 1: Violations by Camera + Violations by Type */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Violations by Camera</CardTitle>
          </CardHeader>
          <CardContent>
            {violationsByCamera.isLoading ? (
              <Skeleton className="h-[300px]" />
            ) : (
              <ReactECharts option={camerasPieOption} style={{ height: "300px" }} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Incidences</CardTitle>
          </CardHeader>
          <CardContent>
            {violationsByType.isLoading ? (
              <Skeleton className="h-[300px]" />
            ) : (
              <ReactECharts option={typeBarOption} style={{ height: "300px" }} />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Hourly Heatmap (full width) */}
      <Card>
        <CardHeader>
          <CardTitle>Hourly Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {hourlyHeatmap.isLoading ? (
            <Skeleton className="h-[200px]" />
          ) : (
            <ReactECharts option={heatmapOption} style={{ height: "200px" }} />
          )}
        </CardContent>
      </Card>

      {/* Row 3: Weekday + Month */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By Weekday</CardTitle>
          </CardHeader>
          <CardContent>
            {weekdayData.isLoading ? (
              <Skeleton className="h-[250px]" />
            ) : (
              <ReactECharts option={weekdayOption} style={{ height: "250px" }} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>By Month</CardTitle>
          </CardHeader>
          <CardContent>
            {monthData.isLoading ? (
              <Skeleton className="h-[250px]" />
            ) : (
              <ReactECharts option={monthOption} style={{ height: "250px" }} />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 4: Quarter + Year */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By Quarter</CardTitle>
          </CardHeader>
          <CardContent>
            {quarterData.isLoading ? (
              <Skeleton className="h-[250px]" />
            ) : (
              <ReactECharts option={quarterOption} style={{ height: "250px" }} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>By Year</CardTitle>
          </CardHeader>
          <CardContent>
            {yearData.isLoading ? (
              <Skeleton className="h-[250px]" />
            ) : (
              <ReactECharts option={yearOption} style={{ height: "250px" }} />
            )}
          </CardContent>
        </Card>
      </div>

    </div>
  );
}
