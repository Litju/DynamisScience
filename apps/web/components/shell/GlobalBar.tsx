"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Database, FlaskConical, Library, Search } from "lucide-react";
import { API_URL } from "@/lib/api";

const NAV = [
  { href: "/research", label: "Research", icon: FlaskConical },
  { href: "/data", label: "Data", icon: Database },
  { href: "/library", label: "Library", icon: Library },
];

export function GlobalBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const pathname = usePathname() ?? "/";
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
      if (!response.ok) throw new Error("unhealthy");
      return (await response.json()) as { status: string; snapshot_id: string; mode: string };
    },
    refetchInterval: 30_000,
    retry: 0,
  });
  return (
    <header className="gbar">
      <Link href="/research" className="brand" style={{ textDecoration: "none" }}>
        <span className="brand-mark" aria-hidden="true">∂</span>
        DynamisScience
        <small>scientific workbench</small>
      </Link>
      <nav className="gnav" aria-label="Primary">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
              <Icon size={14} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="gbar-spacer" />
      <button type="button" className="search-trigger" onClick={onOpenPalette} aria-label="Open command palette">
        <Search size={13} />
        <span>Study, athlete, evidence, metric…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div className={`local-state ${health.isError ? "down" : ""}`} title={`Local science service ${API_URL}`}>
        <i />
        {health.isError ? "service offline" : health.data ? `local · ${health.data.snapshot_id}` : "connecting"}
      </div>
    </header>
  );
}
