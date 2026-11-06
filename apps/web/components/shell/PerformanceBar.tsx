"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { useRole, ROLES } from "./RoleContext";

export function PerformanceBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { role, setRole } = useRole();
  const context = useQuery({ queryKey: ["performance-context"], queryFn: performanceApi.context, staleTime: 300_000 });

  return (
    <header className="pos-topbar">
      <div className="pos-brand">
        <span className="pos-brand-mark">D</span>
        <b>Dynamis Performance OS</b>
        <span>sports science</span>
      </div>
      <div className="pos-club">
        <b>{context.data?.club.name ?? "Northside FC"}</b>
        <span>{context.data?.club.squad ?? "U21"}</span>
        <span className="pos-sep">/</span>
        <span>Performance</span>
      </div>
      <span className="pos-season-pill">
        {context.data?.season.label ?? "2026/27"} · Week {context.data?.season.current_week ?? 16} · {context.data?.season.phase ?? "Build"}
      </span>
      <button type="button" className="pos-search" onClick={onOpenPalette} aria-label="Search athletes, sessions, tests">
        <Search size={12} />
        <span>Search athletes, sessions, tests</span>
        <kbd>Ctrl K</kbd>
      </button>
      <label className="pos-role" title={role.note}>
        <span>Role</span>
        <select
          aria-label="Performance role"
          value={role.id}
          onChange={(event) => setRole(event.target.value as typeof role.id)}
        >
          {ROLES.map((item) => (
            <option key={item.id} value={item.id}>{item.label}</option>
          ))}
        </select>
      </label>
      <div className="pos-avatar" title={role.note}>{role.initials}</div>
    </header>
  );
}
