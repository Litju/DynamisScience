"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type RoleId = "head" | "strength" | "scientist" | "medical" | "analyst" | "director";

export interface RoleDefinition {
  id: RoleId;
  label: string;
  initials: string;
  home: string;
  allowed: string[];
  note: string;
}

export const ROLES: RoleDefinition[] = [
  {
    id: "head",
    label: "Head of Performance",
    initials: "HP",
    home: "/today",
    allowed: ["/today", "/plan", "/monitor", "/test", "/research", "/report", "/atlas", "/data", "/library"],
    note: "Squad load, readiness, availability and reports. Clinical notes are not admitted.",
  },
  {
    id: "strength",
    label: "S&C Coach",
    initials: "SC",
    home: "/today",
    allowed: ["/today", "/plan", "/monitor", "/test", "/report", "/atlas"],
    note: "Session load, readiness and individual response. Medical diagnosis is out of scope.",
  },
  {
    id: "scientist",
    label: "Sports Scientist",
    initials: "SS",
    home: "/monitor",
    allowed: ["/today", "/monitor", "/test", "/research", "/report", "/atlas", "/data", "/library"],
    note: "Full testing, models, diagnostics and evidence. Clinical notes are out of scope.",
  },
  {
    id: "medical",
    label: "Physio / Medical",
    initials: "PM",
    home: "/today",
    allowed: ["/today", "/monitor", "/report", "/atlas"],
    note: "Availability and testing quality only. No injury or RTP table is admitted.",
  },
  {
    id: "analyst",
    label: "Analyst",
    initials: "AN",
    home: "/monitor",
    allowed: ["/today", "/monitor", "/test", "/research", "/report", "/atlas", "/data", "/library"],
    note: "GPS, match and test data. Medical notes are not available.",
  },
  {
    id: "director",
    label: "Director",
    initials: "DR",
    home: "/report",
    allowed: ["/today", "/monitor", "/report", "/atlas"],
    note: "Aggregate availability, load and outcomes. Individual clinical data is not available.",
  },
];

interface RoleContextValue {
  role: RoleDefinition;
  setRole: (role: RoleId) => void;
  canSee: (href: string) => boolean;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [roleId, setRoleId] = useState<RoleId>("head");

  useEffect(() => {
    const stored = window.localStorage.getItem("dynamis-performance-role") as RoleId | null;
    if (stored && ROLES.some((role) => role.id === stored)) setRoleId(stored);
  }, []);

  const value = useMemo<RoleContextValue>(() => {
    const role = ROLES.find((item) => item.id === roleId) ?? ROLES[0];
    return {
      role,
      setRole: (next) => {
        setRoleId(next);
        window.localStorage.setItem("dynamis-performance-role", next);
      },
      canSee: (href) => role.allowed.some((allowed) => href === allowed || href.startsWith(`${allowed}/`)),
    };
  }, [roleId]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const value = useContext(RoleContext);
  if (!value) throw new Error("useRole must be used inside RoleProvider");
  return value;
}

export function roleById(id: RoleId): RoleDefinition {
  return ROLES.find((role) => role.id === id) ?? ROLES[0];
}
