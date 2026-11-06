"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { PerformanceBar } from "@/components/shell/PerformanceBar";
import { PerformanceRail } from "@/components/shell/PerformanceRail";
import { RoleProvider } from "@/components/shell/RoleContext";
import { CommandPalette } from "@/components/shell/CommandPalette";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } } }));
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <QueryClientProvider client={client}>
      <RoleProvider>
        <div className="pos-app">
          <PerformanceBar onOpenPalette={() => setPaletteOpen(true)} />
          <div className="pos-shell">
            <PerformanceRail />
            <div className="pos-content">{children}</div>
          </div>
        </div>
        {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
      </RoleProvider>
    </QueryClientProvider>
  );
}
