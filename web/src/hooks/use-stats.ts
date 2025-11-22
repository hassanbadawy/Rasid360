import { Rasid360Config } from "@/types/rasid360Config";
import {
  CameraDetectThreshold,
  CameraFfmpegThreshold,
  InferenceThreshold,
} from "@/types/graph";
import { Rasid360Stats, PotentialProblem } from "@/types/stats";
import { useMemo } from "react";
import useSWR from "swr";
import useDeepMemo from "./use-deep-memo";
import { capitalizeAll, capitalizeFirstLetter } from "@/utils/stringUtil";
import { useRasid360Stats } from "@/api/ws";

import { useTranslation } from "react-i18next";

export default function useStats(stats: Rasid360Stats | undefined) {
  const { t } = useTranslation(["views/system"]);
  const { data: config } = useSWR<Rasid360Config>("config");

  const memoizedStats = useDeepMemo(stats);

  const potentialProblems = useMemo<PotentialProblem[]>(() => {
    const problems: PotentialProblem[] = [];

    if (!memoizedStats) {
      return problems;
    }

    // if rasid360 has just started
    // don't look for issues
    if (memoizedStats.service.uptime < 120) {
      return problems;
    }

    // check shm level
    const shm = memoizedStats.service.storage["/dev/shm"];
    if (shm?.total && shm?.min_shm && shm.total < shm.min_shm) {
      problems.push({
        text: t("stats.shmTooLow", {
          total: shm.total,
          min: shm.min_shm,
        }),
        color: "text-danger",
        relevantLink: "/system#storage",
      });
    }

    // check detectors for high inference speeds
    Object.entries(memoizedStats["detectors"]).forEach(([key, det]) => {
      if (det["inference_speed"] > InferenceThreshold.error) {
        problems.push({
          text: t("stats.detectIsVerySlow", {
            detect: capitalizeFirstLetter(key),
            speed: det["inference_speed"],
          }),
          color: "text-danger",
          relevantLink: "/system#general",
        });
      } else if (det["inference_speed"] > InferenceThreshold.warning) {
        problems.push({
          text: t("stats.detectIsSlow", {
            detect: capitalizeFirstLetter(key),
            speed: det["inference_speed"],
          }),
          color: "text-orange-400",
          relevantLink: "/system#general",
        });
      }
    });

    // check for offline cameras
    Object.entries(memoizedStats["cameras"]).forEach(([name, cam]) => {
      if (!config) {
        return;
      }

      const cameraName = config.cameras?.[name]?.friendly_name ?? name;
      if (config.cameras[name].enabled && cam["camera_fps"] == 0) {
        problems.push({
          text: t("stats.cameraIsOffline", {
            camera: capitalizeFirstLetter(capitalizeAll(cameraName)),
          }),
          color: "text-danger",
          relevantLink: "logs",
        });
      }
    });

    // check camera cpu usages
    Object.entries(memoizedStats["cameras"]).forEach(([name, cam]) => {
      const ffmpegAvg = parseFloat(
        memoizedStats["cpu_usages"][cam["ffmpeg_pid"]]?.cpu_average,
      );
      const detectAvg = parseFloat(
        memoizedStats["cpu_usages"][cam["pid"]]?.cpu_average,
      );

      const cameraName = config?.cameras?.[name]?.friendly_name ?? name;
      if (!isNaN(ffmpegAvg) && ffmpegAvg >= CameraFfmpegThreshold.error) {
        problems.push({
          text: t("stats.ffmpegHighCpuUsage", {
            camera: capitalizeFirstLetter(capitalizeAll(cameraName)),
            ffmpegAvg,
          }),
          color: "text-danger",
          relevantLink: "/system#cameras",
        });
      }

      if (!isNaN(detectAvg) && detectAvg >= CameraDetectThreshold.error) {
        problems.push({
          text: t("stats.detectHighCpuUsage", {
            camera: capitalizeFirstLetter(capitalizeAll(cameraName)),
            detectAvg,
          }),
          color: "text-danger",
          relevantLink: "/system#cameras",
        });
      }
    });

    return problems;
  }, [config, memoizedStats, t]);

  return { potentialProblems };
}

export function useAutoRasid360Stats() {
  const { data: initialStats } = useSWR<Rasid360Stats>("stats", {
    revalidateOnFocus: false,
  });
  const latestStats = useRasid360Stats();

  const stats = useMemo(() => {
    if (latestStats) {
      return latestStats;
    }

    return initialStats;
  }, [initialStats, latestStats]);

  return stats;
}
