import useSWR from "swr";

/**
 * Hook to fetch available violation types (sub_labels).
 *
 * Resolved server-side from distinct sub_labels of Rasid360 violation events.
 * Previously this fetched 1000 events to the client and derived the list in JS,
 * which both shipped a lot of data and silently dropped violation types that
 * had not occurred recently enough to fall inside that window.
 */
export function useViolations(): string[] {
  const { data } = useSWR<string[]>("events/violation_types", {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 60000, // Cache for 1 minute
  });

  return data ?? [];
}
