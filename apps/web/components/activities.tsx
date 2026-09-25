"use client";

import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronRight, CircleDot, Info, Pause, Play, RotateCcw, Ruler, Target, Timer, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { scienceApi } from "@/lib/api";
import { jointAngleDegrees } from "@/lib/scientific";
import type { MatchFrame, PoseJoint } from "@/lib/types";
import { Button, EmptyState, ErrorState, KeyValue, LoadingState, Panel, SectionHeader, StatusBadge } from "@/components/ui";

const MatchPitch = dynamic(() => import("@/components/MatchPitch"), { ssr: false, loading: () => <div className="canvas-loading"><Waves size={18} />Loading 3D field</div> });

const MATCH_ID = "MATCH-SYNTH-001";
const PLAYBACK_MS = 100;

type PoseFrame = { frame: number; time_s: number; athlete_id: string; joints: PoseJoint[] };

function jointMap(joints: PoseJoint[] | undefined) {
  return new Map((joints ?? []).map((joint) => [joint.joint, joint]));
}

function toVec(joint: PoseJoint | undefined) {
  return joint ? { x: joint.x_m, y: joint.y_m, z: joint.z_m } : undefined;
}

function angleAt(a: PoseJoint | undefined, vertex: PoseJoint | undefined, c: PoseJoint | undefined) {
  return jointAngleDegrees(toVec(a), toVec(vertex), toVec(c));
}

export function MatchLabView({ onNavigate }: { onNavigate: (view: string, id?: string) => void }) {
  const [selectedPlayer, setSelectedPlayer] = useState("PLAYER-14");
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [activeEventId, setActiveEventId] = useState<string | undefined>();

  const match = useQuery({ queryKey: ["match", MATCH_ID], queryFn: () => scienceApi.match(MATCH_ID) });
  const tracking = useQuery({ queryKey: ["tracking", MATCH_ID], queryFn: () => scienceApi.tracking(MATCH_ID) });
  const pose = useQuery({ queryKey: ["pose", MATCH_ID, selectedPlayer], queryFn: () => scienceApi.pose(MATCH_ID, selectedPlayer), enabled: Boolean(selectedPlayer) });

  const frames = useMemo(() => tracking.data?.frames ?? [], [tracking.data]);
  const frameCount = frames.length;
  const currentFrame: MatchFrame | undefined = frames[frameIndex];
  const poseFrames = pose.data?.frames ?? [];
  const currentPose: PoseFrame | undefined = pose.data?.available ? poseFrames[frameIndex] : undefined;
  const poseAvailable = Boolean(pose.data?.available);

  useEffect(() => {
    if (!playing || frameCount === 0) return;
    const timer = window.setInterval(() => {
      setFrameIndex((index) => (index >= frameCount - 1 ? 0 : index + 1));
    }, PLAYBACK_MS);
    return () => window.clearInterval(timer);
  }, [playing, frameCount]);

  useEffect(() => {
    if (frameCount > 0 && frameIndex >= frameCount) setFrameIndex(0);
  }, [frameCount, frameIndex]);

  const playerIds = useMemo(
    () => (frames[0]?.entities ?? []).filter((entity) => entity.player_id !== "BALL").map((entity) => entity.player_id),
    [frames],
  );

  const derived = useMemo(() => {
    if (!currentFrame || frameIndex === 0) {
      const fallback = currentFrame;
      if (!fallback) return null;
      const player = fallback.entities.find((entity) => entity.player_id === selectedPlayer);
      const ball = fallback.entities.find((entity) => entity.player_id === "BALL");
      if (!player || !ball) return null;
      const opponents = fallback.entities.filter((entity) => entity.team !== player.team && entity.player_id !== "BALL");
      const nearest = opponents.reduce<{ player_id: string; distance: number } | null>((current, entity) => {
        const next = Math.hypot(entity.x_m - player.x_m, entity.y_m - player.y_m);
        return !current || next < current.distance ? { player_id: entity.player_id, distance: next } : current;
      }, null);
      return {
        speed: Math.hypot(player.vx_m_s, player.vy_m_s),
        acceleration: null as number | null,
        distance: Math.hypot(player.x_m - ball.x_m, player.y_m - ball.y_m),
        nearest,
      };
    }
    const previous = frames[frameIndex - 1];
    const current = frames[frameIndex];
    const player = current.entities.find((entity) => entity.player_id === selectedPlayer);
    const before = previous.entities.find((entity) => entity.player_id === selectedPlayer);
    const ball = current.entities.find((entity) => entity.player_id === "BALL");
    if (!player || !ball) return null;
    const dt = current.time_s - previous.time_s;
    const acceleration = before && dt > 0
      ? Math.hypot(player.vx_m_s - before.vx_m_s, player.vy_m_s - before.vy_m_s) / dt
      : null;
    const opponents = current.entities.filter((entity) => entity.team !== player.team && entity.player_id !== "BALL");
    const nearest = opponents.reduce<{ player_id: string; distance: number } | null>((accumulator, entity) => {
      const next = Math.hypot(entity.x_m - player.x_m, entity.y_m - player.y_m);
      return !accumulator || next < accumulator.distance ? { player_id: entity.player_id, distance: next } : accumulator;
    }, null);
    return {
      speed: Math.hypot(player.vx_m_s, player.vy_m_s),
      acceleration,
      distance: Math.hypot(player.x_m - ball.x_m, player.y_m - ball.y_m),
      nearest,
    };
  }, [currentFrame, frameIndex, frames, selectedPlayer]);

  const joints = useMemo(() => jointMap(currentPose?.joints), [currentPose]);
  const angles = useMemo(() => {
    if (!poseAvailable) return null;
    return {
      leftKnee: angleAt(joints.get("left_hip"), joints.get("left_knee"), joints.get("left_ankle")),
      rightKnee: angleAt(joints.get("right_hip"), joints.get("right_knee"), joints.get("right_ankle")),
      leftHip: angleAt(joints.get("left_shoulder"), joints.get("left_hip"), joints.get("left_knee")),
      rightHip: angleAt(joints.get("right_shoulder"), joints.get("right_hip"), joints.get("right_knee")),
    };
  }, [joints, poseAvailable]);

  const meanConfidence = useMemo(() => {
    if (!currentPose?.joints.length) return null;
    return (currentPose.joints.reduce((sum, joint) => sum + joint.confidence, 0) / currentPose.joints.length) * 100;
  }, [currentPose]);

  const selectEvent = (eventId: string, startS: number, athleteId: string) => {
    setActiveEventId(eventId);
    setPlaying(false);
    setFrameIndex(Math.max(0, Math.min(frameCount - 1, Math.round(startS * (tracking.data?.sample_rate_hz ?? 10)))));
    if (athleteId && playerIds.includes(athleteId)) setSelectedPlayer(athleteId);
  };

  if (match.isLoading || tracking.isLoading) return <LoadingState label="Loading bounded match segment" />;
  if (match.error || tracking.error) {
    return <ErrorState message="The local MatchLab stream could not be loaded." onRetry={() => { void match.refetch(); void tracking.refetch(); }} />;
  }

  const duration = tracking.data?.duration_s ?? 0;
  const events = tracking.data?.events ?? [];

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Laboratory / MatchLab"
        title="Field context × biomechanical movement"
        description="A synchronized 10 Hz synthetic match segment. The field, ball and pose skeleton share one pitch coordinate frame; select a player to inspect the same event in field and joint space."
        actions={<><StatusBadge tone="cyan">SYNTHETIC</StatusBadge><Button size="sm" onClick={() => onNavigate("lineage", MATCH_ID)}><CircleDot size={13} /> Lineage</Button></>}
      />
      <div className="match-toolbar">
        <div className="segmented">
          <Button size="sm" variant={playing ? "primary" : "secondary"} onClick={() => setPlaying((value) => !value)} disabled={frameCount === 0}>
            {playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "Pause" : "Play segment"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => { setFrameIndex(0); setPlaying(false); setActiveEventId(undefined); }}><RotateCcw size={14} /> Reset</Button>
        </div>
        <div className="match-time">
          <span className="mono">{currentFrame?.time_s.toFixed(1) ?? "0.0"} s</span>
          <span className="muted">/ {duration.toFixed(0)} s</span>
          <span className="live-dot" />{tracking.data?.sample_rate_hz ?? 10} Hz
          <span className="muted">· {tracking.data?.frame_count ?? 0} frames</span>
        </div>
      </div>
      <div className="match-layout">
        <Panel className="pitch-panel" eyebrow="Spatial view / regulation-style pitch" title="Tracking field" action={<span className="mono subtle">1 unit = 10 m</span>}>
          <div className="pitch-canvas">
            <MatchPitch entities={currentFrame?.entities ?? []} poseJoints={currentPose?.joints ?? []} selectedPlayer={selectedPlayer} onSelectPlayer={(id) => { setSelectedPlayer(id); setPlaying(false); }} />
          </div>
          <div className="pitch-legend">
            <span><i className="legend-dot home" />HOME</span>
            <span><i className="legend-dot away" />AWAY</span>
            <span><i className="legend-dot ball" />BALL</span>
            <span className="subtle">Pose skeleton exaggerated 4× · drag to orbit</span>
          </div>
        </Panel>
        <Panel className="pose-panel" eyebrow="Articulated view / confidence-weighted" title={`Pose / ${selectedPlayer}`} action={poseAvailable ? <StatusBadge tone="good">VALID STREAM</StatusBadge> : <StatusBadge tone="warn">NOT RETAINED</StatusBadge>}>
          {poseAvailable ? (
            <>
              <div className="pose-canvas"><PoseView joints={currentPose?.joints ?? []} /></div>
              <div className="pose-confidence"><span>Mean joint confidence</span><strong className="mono">{meanConfidence === null ? "—" : `${meanConfidence.toFixed(1)}%`}</strong></div>
              <div className="pose-legend"><span className="pose-line" /> connected joints <span className="pose-node" /> landmarks <span className="pose-confidence-mark" /> low confidence</div>
            </>
          ) : (
            <div className="empty-state pose-unavailable">
              <Ruler size={20} />
              <strong>No pose stream for {selectedPlayer}</strong>
              <span>{pose.data?.message ?? "Pose is retained for a bounded subset of athletes in this segment."}</span>
              <div className="pose-available-list">
                <span className="eyebrow">Tracked athletes</span>
                <div className="chip-row">
                  {(pose.data?.pose_athletes ?? match.data?.pose_athletes ?? []).map((athlete) => (
                    <button key={athlete} className="chip" onClick={() => setSelectedPlayer(athlete)}>{athlete.replace("PLAYER-", "#")}</button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>
      <div className="match-bottom-grid">
        <Panel eyebrow="Event index" title="Scientific events" action={<span className="subtle">Jump to interval · selects the event athlete</span>}>
          <div className="event-list">
            {events.map((event) => (
              <button
                key={event.event_id}
                className={`event-row ${activeEventId === event.event_id ? "selected" : ""}`}
                onClick={() => selectEvent(event.event_id, event.start_s, event.athlete_id)}
              >
                <span className="event-icon"><Target size={14} /></span>
                <span><strong>{event.label}</strong><small>{event.event_type.replaceAll("_", " ")} · {event.athlete_id.replace("PLAYER-", "#")}</small></span>
                <span className="mono">{event.start_s.toFixed(0)}–{event.end_s.toFixed(0)} s</span>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </Panel>
        <Panel eyebrow="Derived context" title="Current frame measures" action={<StatusBadge tone="warn">DERIVED</StatusBadge>}>
          {derived ? (
            <div className="derived-grid">
              <div><span>Player speed</span><strong>{derived.speed.toFixed(2)} <small>m·s⁻¹</small></strong></div>
              <div><span>Acceleration</span><strong>{derived.acceleration === null ? "—" : derived.acceleration.toFixed(2)} <small>m·s⁻²</small></strong></div>
              <div><span>Distance to ball</span><strong>{derived.distance.toFixed(1)} <small>m</small></strong></div>
              <div><span>Nearest opponent</span><strong>{derived.nearest ? `${derived.nearest.player_id.replace("PLAYER-", "#")} · ${derived.nearest.distance.toFixed(1)} m` : "—"}</strong></div>
            </div>
          ) : (
            <EmptyState title="Select a player" detail="Choose an entity in the pitch to derive event context." />
          )}
          <div className="formula-note"><Activity size={14} /><span>Acceleration is the finite difference of the tracking velocity between adjacent 10 Hz frames; it is not a filtered biomechanical derivative.</span></div>
        </Panel>
      </div>
      <div className="match-bottom-grid">
        <Panel eyebrow="Joint-space approximation" title="Sagittal chain angles" action={<StatusBadge tone={poseAvailable ? "cyan" : "warn"}>{poseAvailable ? "COMPUTED" : "UNAVAILABLE"}</StatusBadge>}>
          {angles && poseAvailable ? (
            <div className="derived-grid">
              <div><span>Left knee flexion</span><strong>{angles.leftKnee === null ? "—" : angles.leftKnee.toFixed(1)} <small>°</small></strong></div>
              <div><span>Right knee flexion</span><strong>{angles.rightKnee === null ? "—" : angles.rightKnee.toFixed(1)} <small>°</small></strong></div>
              <div><span>Left hip angle</span><strong>{angles.leftHip === null ? "—" : angles.leftHip.toFixed(1)} <small>°</small></strong></div>
              <div><span>Right hip angle</span><strong>{angles.rightHip === null ? "—" : angles.rightHip.toFixed(1)} <small>°</small></strong></div>
            </div>
          ) : (
            <EmptyState title="Pose required" detail="Joint angles are computed from the retained pose stream for the selected athlete." />
          )}
          <div className="formula-note"><Info size={14} /><span>Angles are the geometric angle at the joint between the two adjacent segments of the synthetic pose stream.</span></div>
        </Panel>
        <Panel eyebrow="Frame provenance" title="Selected athlete" action={<span className="mono subtle">frame {frameIndex}</span>}>
          <div className="key-value-grid">
            <KeyValue label="Athlete" value={selectedPlayer} mono />
            <KeyValue label="Frame time" value={currentFrame ? `${currentFrame.time_s.toFixed(1)} s` : "—"} mono />
            <KeyValue label="Pose frame" value={currentPose ? `${currentPose.frame}` : "not retained"} mono />
            <KeyValue label="Pose joints" value={currentPose ? String(currentPose.joints.length) : "0"} mono />
            <KeyValue label="Snapshot" value={String(match.data?.provenance?.snapshot_id ?? "DS-SYNTH-001")} mono />
            <KeyValue label="Source" value="match_tracking.parquet" mono />
          </div>
          <div className="formula-note"><Timer size={14} /><span>Field, ball and pose frames are indexed by the same 10 Hz sample clock.</span></div>
        </Panel>
      </div>
      <Panel className="timeline-panel" eyebrow="Playback" title="Synchronized timeline" action={<span className="mono subtle">frame {frameIndex} / {Math.max(0, frameCount - 1)}</span>}>
        <div className="timeline-track">
          <input
            className="timeline-range"
            type="range"
            min={0}
            max={Math.max(0, frameCount - 1)}
            value={frameIndex}
            onChange={(event) => { setFrameIndex(Number(event.target.value)); setPlaying(false); }}
          />
          <div className="timeline-events" aria-hidden="true">
            {events.map((event) => (
              <button
                key={event.event_id}
                className={`timeline-event ${activeEventId === event.event_id ? "active" : ""}`}
                style={{ left: `${duration ? (event.start_s / duration) * 100 : 0}%`, width: `${duration ? ((event.end_s - event.start_s) / duration) * 100 : 0}%` }}
                onClick={() => selectEvent(event.event_id, event.start_s, event.athlete_id)}
                title={`${event.label} ${event.start_s}–${event.end_s} s`}
              />
            ))}
          </div>
          <div className="timeline-cursor" style={{ left: `${duration ? ((currentFrame?.time_s ?? 0) / duration) * 100 : 0}%` }} aria-hidden="true" />
        </div>
        <div className="timeline-marks">
          <span>0 s</span>
          {events.map((event) => <span key={event.event_id}>{event.label} · {event.start_s.toFixed(0)} s</span>)}
          <span>{duration.toFixed(0)} s</span>
        </div>
      </Panel>
    </div>
  );
}

const CONNECTIONS: [string, string][] = [
  ["hip", "left_hip"],
  ["hip", "right_hip"],
  ["hip", "knee"],
  ["knee", "ankle"],
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
 * Sagittal joint-space view. Coordinates are normalised to the athlete's own
 * bounding box so the skeleton always fills the viewport; the anchor is the
 * hip, so the drawing is stable while the athlete moves across the pitch.
 */
function PoseView({ joints }: { joints: PoseJoint[] }) {
  if (joints.length === 0) {
    return <div className="pose-empty"><Waves size={18} /><span>No pose frame for this index</span></div>;
  }
  const anchor = joints.find((joint) => joint.joint === "hip") ?? joints[0];
  const local = joints.map((joint) => ({ joint, x: joint.x_m - anchor.x_m, y: joint.z_m }));
  const xs = local.map((item) => item.x);
  const ys = local.map((item) => item.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(0.2, maxX - minX);
  const spanY = Math.max(0.4, maxY - minY);
  const padding = 12;
  const width = 100 - padding * 2;
  const height = 150 - padding * 2;
  const scale = Math.min(width / spanX, height / spanY);
  const project = (item: { x: number; y: number }) => ({
    cx: padding + (item.x - minX) * scale + (width - spanX * scale) / 2,
    cy: 150 - padding - (item.y - minY) * scale - (height - spanY * scale) / 2,
  });
  const projected = new Map(local.map((item) => [item.joint.joint, { ...project(item), confidence: item.joint.confidence }]));
  return (
    <svg className="pose-svg" viewBox="0 0 100 150" role="img" aria-label={`Synthetic sagittal skeleton, ${joints.length} joints`}>
      <defs>
        <linearGradient id="poseGrid" x1="0" x2="1">
          <stop offset="0" stopColor="#17313a" />
          <stop offset="1" stopColor="#101c26" />
        </linearGradient>
      </defs>
      <rect width="100" height="150" fill="url(#poseGrid)" />
      <path d="M0 30H100M0 60H100M0 90H100M0 120H100M20 0V150M40 0V150M60 0V150M80 0V150" stroke="rgba(116,160,164,.13)" strokeWidth=".4" />
      <text x="4" y="10" fill="#6f8594" fontSize="4">sagittal · hip-anchored · {spanY.toFixed(2)} m span</text>
      {CONNECTIONS.map(([from, to]) => {
        const a = projected.get(from);
        const b = projected.get(to);
        if (!a || !b) return null;
        return <line key={`${from}-${to}`} x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy} stroke="#9ce7dc" strokeWidth="1" strokeLinecap="round" />;
      })}
      {[...projected.entries()].map(([name, point]) => (
        <g key={name}>
          <circle cx={point.cx} cy={point.cy} r={point.confidence > 0.85 ? 1.5 : 1} fill={point.confidence > 0.85 ? "#effffb" : "#8fb8b3"} />
        </g>
      ))}
      {["knee", "ankle", "shoulder", "left_knee", "right_knee"].map((name) => {
        const point = projected.get(name);
        if (!point) return null;
        return <text key={name} x={point.cx + 2.4} y={point.cy + 1.2} fill="#7fa2a6" fontSize="3.4">{name.replace("_", " ")}</text>;
      })}
    </svg>
  );
}
