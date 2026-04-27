"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Polls the router to re-fetch server components on a fixed interval.
 *
 * Uses ``router.refresh()`` from Next 14's App Router which triggers a
 * server re-render and keeps client state intact. Pause when the tab is
 * hidden so we don't burn requests in background tabs.
 */
export function AutoRefresh({ intervalMs = 10_000 }: { intervalMs?: number }) {
  const router = useRouter();
  const [counter, setCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) return;
      router.refresh();
      setCounter((c) => c + 1);
    };
    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [router, intervalMs]);

  return (
    <span
      className="hidden"
      data-auto-refresh
      data-tick={counter}
      aria-hidden="true"
    />
  );
}
