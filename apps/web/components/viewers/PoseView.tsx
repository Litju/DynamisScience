"use client";

import type { PoseJoint } from "@/lib/types";

export const POSE_CONNECTIONS: [string, string][] = [
  ["hip", "left_hip"],
  ["hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
  ["hip", "shoulder"],
  ["shoulder", "left_shoulder"],
  ["shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
];

/**
 * Sagittal (x–z) projection anchored at the hip. The scale is fixed in metres
 * (not re-fitted per frame), so joint excursions are comparable across frames.
 */
/** The generator also emits aggregate "knee"/"ankle" markers; they duplicate the limbs and are not drawn. */
export const AGGREGATE_MARKERS = new Set(["knee", "ankle"]);

export function PoseView({ joints, athleteId }: { joints: PoseJoint[]; athleteId: string }) {
  if (joints.length === 0) return <div className="pose-unavailable">No pose sample at this frame.</div>;
  const anchor = joints.find((joint) => joint.joint === "hip") ?? joints[0];
  const width = 220;
  const height = 300;
  const metresToPx = 130;
  const groundY = height - 34;
  const project = (joint: PoseJoint) => ({ x: width / 2 + (joint.x_m - anchor.x_m) * metresToPx, y: groundY - joint.z_m * metresToPx });
  const points = new Map(joints.filter((joint) => !AGGREGATE_MARKERS.has(joint.joint)).map((joint) => [joint.joint, { ...project(joint), confidence: joint.confidence }]));
  const ticks = [0, 0.5, 1, 1.5, 2];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" role="img" aria-label={`Sagittal pose of ${athleteId}, ${joints.length} joints`} preserveAspectRatio="xMidYMid meet">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={24} x2={width - 8} y1={groundY - tick * metresToPx} y2={groundY - tick * metresToPx} stroke="rgba(150,170,180,0.10)" strokeWidth={0.6} />
          <text x={4} y={groundY - tick * metresToPx + 3} fill="#56636b" fontSize={8} fontFamily="IBM Plex Mono, monospace">{tick.toFixed(1)}</text>
        </g>
      ))}
      <line x1={24} x2={width - 8} y1={groundY} y2={groundY} stroke="#3a4750" strokeWidth={1} />
      <text x={4} y={height - 10} fill="#56636b" fontSize={8} fontFamily="IBM Plex Mono, monospace">z (m) · x relative to hip · 1:1 scale</text>
      {POSE_CONNECTIONS.map(([from, to]) => {
        const a = points.get(from);
        const b = points.get(to);
        if (!a || !b) return null;
        const low = Math.min(a.confidence, b.confidence) < 0.85;
        return <line key={`${from}-${to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={low ? "#7d8a92" : "#4fc4b6"} strokeWidth={2.2} strokeLinecap="round" strokeDasharray={low ? "3 2" : undefined} />;
      })}
      {[...points.entries()].map(([name, point]) => (
        <circle key={name} cx={point.x} cy={point.y} r={name === "hip" ? 3.4 : 2.4} fill={point.confidence > 0.85 ? "#f3f6f7" : "#7d8a92"}>
          <title>{`${name.replaceAll("_", " ")} · confidence ${(point.confidence * 100).toFixed(0)}%`}</title>
        </circle>
      ))}
    </svg>
  );
}
