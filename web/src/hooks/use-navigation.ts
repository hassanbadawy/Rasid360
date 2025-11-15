import { ENV } from "@/env";
import { FrigateConfig } from "@/types/frigateConfig";
import { NavData } from "@/types/navigation";
import { useMemo } from "react";
import { isDesktop } from "react-device-detect";
import { FaCompactDisc, FaVideo } from "react-icons/fa";
import { IoSearch } from "react-icons/io5";
import { LuConstruction, LuLayoutDashboard } from "react-icons/lu";
import { MdCategory, MdVideoLibrary } from "react-icons/md";
import { TbFaceId } from "react-icons/tb";
import useSWR from "swr";
import { useIsAdmin } from "./use-is-admin";

export const ID_LIVE = 1;
export const ID_REVIEW = 2;
export const ID_EXPLORE = 3;
export const ID_DASHBOARD = 4;
export const ID_EXPORT = 5;
export const ID_PLAYGROUND = 6;
export const ID_FACE_LIBRARY = 7;
export const ID_CLASSIFICATION = 8;

export default function useNavigation(
  variant: "primary" | "secondary" = "primary",
) {
  const { data: config } = useSWR<FrigateConfig>("config", {
    revalidateOnFocus: false,
  });
  const isAdmin = useIsAdmin();

  return useMemo(
    () =>
      [
        {
          id: ID_DASHBOARD,
          variant,
          icon: LuLayoutDashboard,
          title: "menu.dashboard",
          url: "/",
        },
        {
          id: ID_LIVE,
          variant,
          icon: FaVideo,
          title: "menu.live.title",
          url: "/live",
        },
        {
          id: ID_EXPLORE,
          variant,
          icon: IoSearch,
          title: "menu.tickets",
          url: "/tickets",
        },
        {
          id: ID_REVIEW,
          variant,
          icon: MdVideoLibrary,
          title: "menu.playback",
          url: "/playback",
        },
        {
          id: ID_EXPORT,
          variant,
          icon: FaCompactDisc,
          title: "menu.export",
          url: "/export",
        },
        {
          id: ID_PLAYGROUND,
          variant,
          icon: LuConstruction,
          title: "menu.uiPlayground",
          url: "/playground",
          enabled: ENV !== "production",
        },
        {
          id: ID_FACE_LIBRARY,
          variant,
          icon: TbFaceId,
          title: "menu.faceLibrary",
          url: "/faces",
          enabled: isDesktop && config?.face_recognition.enabled && isAdmin,
        },
        {
          id: ID_CLASSIFICATION,
          variant,
          icon: MdCategory,
          title: "menu.classification",
          url: "/classification",
          enabled: isDesktop && isAdmin,
        },
      ] as NavData[],
    [config?.face_recognition?.enabled, variant, isAdmin],
  );
}
