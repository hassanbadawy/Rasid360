import { useContext } from "react";
import { AuthContext } from "@/context/auth-context";
import useSWR from "swr";
import { Rasid360Config } from "@/types/rasid360Config";

export function useAllowedCameras() {
  const { auth } = useContext(AuthContext);
  const { data: config } = useSWR<Rasid360Config>("config", {
    revalidateOnFocus: false,
  });

  if (
    auth.user?.role === "viewer" ||
    auth.user?.role === "admin" ||
    !auth.isAuthenticated // anonymous port 5000
  ) {
    // return all cameras
    return config?.cameras ? Object.keys(config.cameras) : [];
  }

  return auth.allowedCameras || [];
}
