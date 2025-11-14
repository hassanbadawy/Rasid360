import { useMemo } from "react";
import useSWR from "swr";

interface Event {
  sub_label?: string;
}

/**
 * Hook to fetch available violation types (sub_labels) from events
 * Returns sorted list of unique violation names from DSL configuration
 */
export function useViolations(): string[] {
  const { data: events } = useSWR<Event[]>(
    "events?limit=1000&include_thumbnails=0",
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 60000, // Cache for 1 minute
    }
  );

  const violations = useMemo(() => {
    if (!events) {
      return [];
    }

    // Extract unique sub_labels (violations) from events
    const uniqueViolations = new Set<string>();
    events.forEach((event) => {
      if (event.sub_label) {
        uniqueViolations.add(event.sub_label);
      }
    });

    return Array.from(uniqueViolations).sort();
  }, [events]);

  return violations;
}
