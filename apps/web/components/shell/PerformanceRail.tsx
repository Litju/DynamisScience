"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CalendarRange,
  Clock3,
  Database,
  FileText,
  FlaskConical,
  Grid3x3,
  Library,
  TestTubes,
} from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { useRole } from "./RoleContext";

const NAV = [
  {
    label: "Daily",
    items: [
      { href: "/today", label: "Today", icon: Clock3, tag: "LIVE" },
      { href: "/plan", label: "Plan", icon: CalendarRange, tag: "W16" },
      { href: "/monitor", label: "Monitor", icon: Activity, tag: "28" },
      { href: "/test", label: "Test", icon: TestTubes, tag: "CMJ" },
    ],
  },
  {
    label: "Evidence",
    items: [
      { href: "/research", label: "Research", icon: FlaskConical, tag: "" },
      { href: "/report", label: "Reports", icon: FileText, tag: "" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/atlas", label: "Component atlas", icon: Grid3x3, tag: "ALL" },
      { href: "/data", label: "Data admission", icon: Database, tag: "" },
      { href: "/library", label: "Registry", icon: Library, tag: "" },
    ],
  },
];

export function PerformanceRail() {
  const pathname = usePathname() ?? "/today";
  const { canSee } = useRole();
  const today = useQuery({ queryKey: ["performance-today"], queryFn: performanceApi.today, staleTime: 60_000 });
  const reports = useQuery({ queryKey: ["performance-reports"], queryFn: () => performanceApi.reports(), staleTime: 60_000 });
  const tags: Record<string, string> = {
    "/research": today.data ? String(today.data.study.evidence_count) : "—",
    "/report": reports.data ? String(reports.data.length) : "—",
  };

  return (
    <aside className="pos-rail" aria-label="Performance navigation">
      <div className="pos-club-badge">
        <span className="pos-crest">NFC</span>
        <div>
          <b>Northside FC</b>
          <span>U21 · 28 athletes</span>
        </div>
      </div>
      <nav className="pos-rail-nav" aria-label="Workspaces">
        {NAV.map((group) => {
          const items = group.items.filter((item) => canSee(item.href));
          if (!items.length) return null;
          return (
            <div key={group.label} className="pos-rail-group">
              <div className="pos-rail-label">{group.label}</div>
              {items.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const tag = tags[item.href] ?? item.tag;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`pos-rail-item ${active ? "is-active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    title={item.label}
                  >
                    <span className="pos-rail-ico"><Icon size={14} strokeWidth={1.5} /></span>
                    <span className="pos-rail-name">{item.label}</span>
                    {tag ? <span className="pos-rail-tag">{tag}</span> : null}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>
      <div className="pos-squad-block">
        <div className="pos-k">Squad availability</div>
        <div className="pos-squad-number">28<span>/ 28 active</span></div>
        <div className="pos-squad-bar" aria-hidden="true">
          {Array.from({ length: 14 }).map((_, index) => <i key={index} />)}
        </div>
        <div className="pos-squad-note">
          <b>No injury table admitted</b>
          <br />
          Availability below is roster status only.
        </div>
      </div>
    </aside>
  );
}
