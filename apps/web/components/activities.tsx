"use client";

import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronRight, CircleDot, Pause, Play, RotateCcw, Target, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { scienceApi } from "@/lib/api";
import type { MatchFrame, PoseJoint } from "@/lib/types";
import { Button, EmptyState, ErrorState, LoadingState, Panel, SectionHeader, StatusBadge } from "@/components/ui";

const MatchPitch = dynamic(() => import("@/components/MatchPitch"), { ssr: false, loading: () => <div className="canvas-loading"><Waves size={18} />Loading 3D field</div> });

type PoseFrame = { frame: number; time_s: number; athlete_id: string; joints: PoseJoint[] };

export function MatchLabView({ onNavigate }: { onNavigate: (view: string) => void }) {
  const [selectedPlayer, setSelectedPlayer] = useState("PLAYER-14");
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const tracking = useQuery({ queryKey: ["tracking", "MATCH-SYNTH-001"], queryFn: () => scienceApi.tracking("MATCH-SYNTH-001") });
  const pose = useQuery({ queryKey: ["pose", "MATCH-SYNTH-001", selectedPlayer], queryFn: () => scienceApi.pose("MATCH-SYNTH-001", selectedPlayer), enabled: Boolean(selectedPlayer) });
  const currentFrame: MatchFrame | undefined = tracking.data?.frames[frameIndex];
  const currentPose: PoseFrame | undefined = pose.data?.frames[frameIndex];
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setFrameIndex((index) => index >= (tracking.data?.frames.length ?? 1) - 1 ? 0 : index + 1), 90);
    return () => window.clearInterval(timer);
  }, [playing, tracking.data?.frames.length]);
  useEffect(() => {
    if (tracking.data && frameIndex >= tracking.data.frames.length) setFrameIndex(0);
  }, [tracking.data, frameIndex]);
  const derived = useMemo(() => {
    if (!currentFrame) return null;
    const player = currentFrame.entities.find((entity) => entity.player_id === selectedPlayer);
    const ball = currentFrame.entities.find((entity) => entity.player_id === "BALL");
    if (!player || !ball) return null;
    const distance = Math.hypot(player.x_m - ball.x_m, player.y_m - ball.y_m);
    const opponents = currentFrame.entities.filter((entity) => entity.team !== player.team && entity.player_id !== "BALL");
    const nearest = opponents.reduce<{ entity: typeof opponents[number]; distance: number } | null>((current, entity) => { const next = Math.hypot(entity.x_m - player.x_m, entity.y_m - player.y_m); return !current || next < current.distance ? { entity, distance: next } : current; }, null);
    return { speed: Math.hypot(player.vx_m_s, player.vy_m_s), distance, nearest, acceleration: Math.hypot(player.vx_m_s, player.vy_m_s) * 0.08 };
  }, [currentFrame, selectedPlayer]);
  if (tracking.isLoading) return <LoadingState label="Loading bounded match segment" />;
  if (tracking.error) return <ErrorState message="The local MatchLab stream could not be loaded." onRetry={() => tracking.refetch()} />;
  return <div className="view-stack">
    <SectionHeader eyebrow="Laboratory / MatchLab" title="Field context × biomechanical movement" description="A synchronized 10 Hz synthetic match segment. Select a player to inspect the same event in field and joint-space views." actions={<><StatusBadge tone="cyan">SYNTHETIC</StatusBadge><Button size="sm" onClick={() => onNavigate("lineage")}><CircleDot size={13} /> Lineage</Button></>} />
    <div className="match-toolbar"><div className="segmented"><Button size="sm" variant={playing ? "primary" : "secondary"} onClick={() => setPlaying((value) => !value)}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "Pause" : "Play segment"}</Button><Button size="sm" variant="ghost" onClick={() => { setFrameIndex(0); setPlaying(false); }}><RotateCcw size={14} /> Reset</Button></div><div className="match-time"><span className="mono">{currentFrame?.time_s.toFixed(1) ?? "0.0"} s</span><span className="muted">/ {tracking.data?.duration_s.toFixed(0)} s</span><span className="live-dot" />10 Hz</div></div>
    <div className="match-layout">
      <Panel className="pitch-panel" eyebrow="Spatial view / regulation-style pitch" title="Tracking field" action={<span className="mono subtle">{tracking.data?.frame_count ?? 0} frames</span>}>
        <div className="pitch-canvas"><MatchPitch entities={currentFrame?.entities ?? []} poseJoints={currentPose?.joints ?? []} selectedPlayer={selectedPlayer} onSelectPlayer={setSelectedPlayer} /></div>
        <div className="pitch-legend"><span><i className="legend-dot home" />HOME</span><span><i className="legend-dot away" />AWAY</span><span><i className="legend-dot ball" />BALL</span><span className="subtle">Drag to orbit · scroll to inspect</span></div>
      </Panel>
      <Panel className="pose-panel" eyebrow="Articulated view / confidence-weighted" title={`Pose / ${selectedPlayer}`} action={<StatusBadge tone="good">VALID STREAM</StatusBadge>}>
        <div className="pose-canvas"><PoseView joints={currentPose?.joints ?? []} /></div>
        <div className="pose-confidence"><span>Mean joint confidence</span><strong className="mono">{currentPose?.joints.length ? (currentPose.joints.reduce((sum, joint) => sum + joint.confidence, 0) / currentPose.joints.length * 100).toFixed(1) : "—"}%</strong></div>
        <div className="pose-legend"><span className="pose-line" /> connected joints <span className="pose-node" /> landmarks <span className="pose-confidence-mark" /> confidence retained</div>
      </Panel>
    </div>
    <div className="match-bottom-grid">
      <Panel eyebrow="Event index" title="Scientific events" action={<span className="subtle">Jump to interval</span>}>
        <div className="event-list">{(tracking.data?.events ?? []).map((event) => <button key={event.event_id} className="event-row" onClick={() => setFrameIndex(Math.round(event.start_s * 10))}><span className="event-icon"><Target size={14} /></span><span><strong>{event.label}</strong><small>{event.event_type.replaceAll("_", " ")}</small></span><span className="mono">{event.start_s.toFixed(0)}–{event.end_s.toFixed(0)} s</span><ChevronRight size={14} /></button>)}</div>
      </Panel>
      <Panel eyebrow="Derived context" title="Current event measures" action={<StatusBadge tone="warn">DERIVED</StatusBadge>}>
        {derived ? <div className="derived-grid"><div><span>Player speed</span><strong>{derived.speed.toFixed(2)} <small>m·s⁻¹</small></strong></div><div><span>Acceleration proxy</span><strong>{derived.acceleration.toFixed(2)} <small>m·s⁻²</small></strong></div><div><span>Distance to ball</span><strong>{derived.distance.toFixed(1)} <small>m</small></strong></div><div><span>Nearest opponent</span><strong>{derived.nearest?.entity.player_id.replace("PLAYER-", "#") ?? "—"} <small>at {derived.nearest?.distance.toFixed(1) ?? "—"} m</small></strong></div></div> : <EmptyState title="Select a player" detail="Choose an entity in the pitch to derive event context." />}
        <div className="formula-note"><Activity size={14} /><span>Derived locally from tracking coordinates; no inferred injury or readiness label.</span></div>
      </Panel>
    </div>
    <Panel className="timeline-panel" eyebrow="Playback" title="Synchronized timeline" action={<span className="mono subtle">frame {frameIndex} / {tracking.data?.frames.length}</span>}>
      <input className="timeline-range" type="range" min={0} max={Math.max(0, (tracking.data?.frames.length ?? 1) - 1)} value={frameIndex} onChange={(event) => { setFrameIndex(Number(event.target.value)); setPlaying(false); }} />
      <div className="timeline-marks"><span>0 s</span><span>possession change</span><span>progressive run</span><span>sprint</span><span>shot</span><span>{(tracking.data?.duration_s ?? 180).toFixed(0)} s</span></div>
    </Panel>
  </div>;
}

function PoseView({ joints }: { joints: PoseJoint[] }) {
  const connections = [["hip", "left_hip"], ["hip", "right_hip"], ["hip", "knee"], ["knee", "ankle"], ["left_hip", "left_knee"], ["left_knee", "left_ankle"], ["right_hip", "right_knee"], ["right_knee", "right_ankle"], ["hip", "shoulder"], ["shoulder", "left_shoulder"], ["shoulder", "right_shoulder"], ["left_shoulder", "left_elbow"], ["left_elbow", "left_wrist"], ["right_shoulder", "right_elbow"], ["right_elbow", "right_wrist"]];
  const points = joints.map((joint) => ({ x: 50 + (joint.x_m - (joint.joint === "hip" ? joint.x_m : 0)) * 2.6, y: 145 - joint.z_m * 55, z: joint.y_m * 2.2 }));
  const byJoint = new Map(joints.map((joint, index) => [joint.joint, points[index]]));
  return <svg className="pose-svg" viewBox="0 0 100 150" role="img" aria-label="Synthetic 3D skeleton pose"><defs><linearGradient id="poseGrid" x1="0" x2="1"><stop offset="0" stopColor="#17313a" /><stop offset="1" stopColor="#101c26" /></linearGradient></defs><rect width="100" height="150" fill="url(#poseGrid)" /><path d="M0 30H100M0 60H100M0 90H100M0 120H100M20 0V150M40 0V150M60 0V150M80 0V150" stroke="rgba(116,160,164,.13)" strokeWidth=".4" />{connections.map(([from, to]) => { const a = byJoint.get(from); const b = byJoint.get(to); return a && b ? <line key={`${from}-${to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#9ce7dc" strokeWidth="1.1" /> : null; })}{joints.map((joint, index) => <circle key={joint.joint} cx={points[index].x} cy={points[index].y} r={joint.confidence > 0.85 ? 1.7 : 1.1} fill="#effffb" />)}</svg>;
}
