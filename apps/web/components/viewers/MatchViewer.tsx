"use client";

import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Info, Pause, Play, SkipBack } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MatchEntity, MatchEvent, MatchFrame, PoseJoint } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig, jointAngleDegrees } from "@/lib/scientific";
import { Button, ErrorBox, KV, Loading, State } from "@/components/ui";
import { useWorkbench } from "@/components/workbench/context";
import { PoseView } from "./PoseView";

const MatchPitch = dynamic(() => import("@/components/MatchPitch"), { ssr: false, loading: () => <div className="pose-unavailable">Loading 3D field</div> });

const MATCH_ID = "MATCH-SYNTH-001";

export interface FrameMeasures {
  speed: number;
  acceleration: number | null;
  distanceToBall: number | null;
  nearestOpponent: { id: string; distance: number } | null;
}

/** Kinematic context for one player: speed from tracking velocity, acceleration by finite difference. */
export function frameMeasures(frames: MatchFrame[], index: number, playerId: string): FrameMeasures | null {
  const current = frames[index];
  const player = current?.entities.find((entity) => entity.player_id === playerId);
  if (!current || !player) return null;
  const ball = current.entities.find((entity) => entity.player_id === "BALL");
  const previous = index > 0 ? frames[index - 1].entities.find((entity) => entity.player_id === playerId) : undefined;
  const dt = index > 0 ? current.time_s - frames[index - 1].time_s : 0;
  const opponents = current.entities.filter((entity) => entity.team !== player.team && entity.player_id !== "BALL");
  const nearest = opponents.reduce<{ id: string; distance: number } | null>((best, entity) => {
    const distance = Math.hypot(entity.x_m - player.x_m, entity.y_m - player.y_m);
    return !best || distance < best.distance ? { id: entity.player_id, distance } : best;
  }, null);
  return {
    speed: Math.hypot(player.vx_m_s, player.vy_m_s),
    acceleration: previous && dt > 0 ? Math.hypot(player.vx_m_s - previous.vx_m_s, player.vy_m_s - previous.vy_m_s) / dt : null,
    distanceToBall: ball ? Math.hypot(player.x_m - ball.x_m, player.y_m - ball.y_m) : null,
    nearestOpponent: nearest,
  };
}

function angle(joints: Map<string, PoseJoint>, a: string, vertex: string, c: string) {
  const vec = (name: string) => {
    const joint = joints.get(name);
    return joint ? { x: joint.x_m, y: joint.y_m, z: joint.z_m } : undefined;
  };
  return jointAngleDegrees(vec(a), vec(vertex), vec(c));
}

export function MatchViewer({ initialEventId, initialAthleteId }: { initialEventId?: string; initialAthleteId?: string }) {
  const wb = useWorkbench();
  const match = useQuery({ queryKey: ["match", MATCH_ID], queryFn: () => scienceApi.match(MATCH_ID) });
  const tracking = useQuery({ queryKey: ["tracking", MATCH_ID], queryFn: () => scienceApi.tracking(MATCH_ID), staleTime: Infinity });
  const [player, setPlayer] = useState(initialAthleteId ?? "PLAYER-14");
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [eventId, setEventId] = useState<string | undefined>(initialEventId);
  const pose = useQuery({ queryKey: ["pose", MATCH_ID, player], queryFn: () => scienceApi.pose(MATCH_ID, player), staleTime: Infinity });
  const closeRef = useRef<HTMLButtonElement>(null);
  const restore = useRef<HTMLElement | null>(null);

  const frames = useMemo(() => tracking.data?.frames ?? [], [tracking.data]);
  const rate = tracking.data?.sample_rate_hz ?? 10;
  const duration = tracking.data?.duration_s ?? 0;
  const events = useMemo(() => tracking.data?.events ?? [], [tracking.data]);
  const activeEvent = events.find((event) => event.event_id === eventId);
  const frame = frames[frameIndex];

  const close = useCallback(() => wb.closeViewer(), [wb]);
  useEffect(() => {
    restore.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (document.querySelector(".palette-backdrop, .drawer-backdrop")) return;
      if (event.key === "Escape") close();
      if (event.key === " " && (event.target as HTMLElement).tagName !== "INPUT") {
        event.preventDefault();
        setPlaying((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      restore.current?.focus?.({ preventScroll: true });
    };
  }, [close]);

  const seekEvent = useCallback((event: MatchEvent) => {
    setEventId(event.event_id);
    setFrameIndex(Math.max(0, Math.round(event.start_s * rate)));
    setPlayer(event.athlete_id);
    setPlaying(false);
    wb.select({ matchEventId: event.event_id });
  }, [rate, wb]);

  // Open on the requested event once tracking is available.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !events.length) return;
    opened.current = true;
    const initial = events.find((event) => event.event_id === initialEventId);
    if (initial) seekEvent(initial);
  }, [events, initialEventId, seekEvent]);

  // Playback runs to the end of the selected event interval (or the segment) and stops there.
  useEffect(() => {
    if (!playing || !frames.length) return;
    const stopIndex = activeEvent ? Math.min(frames.length - 1, Math.round(activeEvent.end_s * rate)) : frames.length - 1;
    const timer = window.setInterval(() => {
      setFrameIndex((index) => {
        if (index >= stopIndex) {
          setPlaying(false);
          return stopIndex;
        }
        return index + 1;
      });
    }, 1000 / rate);
    return () => window.clearInterval(timer);
  }, [activeEvent, frames.length, playing, rate]);

  const poseFrame = pose.data?.available ? pose.data.frames[frameIndex] : undefined;
  const poseTimeMatches = poseFrame && frame ? Math.abs(poseFrame.time_s - frame.time_s) < 1e-6 : false;
  const joints = useMemo(() => new Map((poseFrame?.joints ?? []).map((joint) => [joint.joint, joint])), [poseFrame]);
  const angles = poseFrame
    ? {
        leftKnee: angle(joints, "left_hip", "left_knee", "left_ankle"),
        rightKnee: angle(joints, "right_hip", "right_knee", "right_ankle"),
        leftHip: angle(joints, "left_shoulder", "left_hip", "left_knee"),
        rightHip: angle(joints, "right_shoulder", "right_hip", "right_knee"),
      }
    : null;
  const confidence = poseFrame ? poseFrame.joints.reduce((sum, joint) => sum + joint.confidence, 0) / poseFrame.joints.length : null;
  const measures = frameMeasures(frames, frameIndex, player);
  const players = useMemo(() => (frames[0]?.entities ?? []).filter((entity: MatchEntity) => entity.player_id !== "BALL"), [frames]);
  const eventNow = events.find((event) => frame && frame.time_s >= event.start_s && frame.time_s <= event.end_s);
  const pct = (seconds: number) => `${duration ? (seconds / duration) * 100 : 0}%`;

  return (
    <section className="viewer" role="dialog" aria-modal="false" aria-label="Spatial and biomechanical viewer">
      <header className="viewer-head">
        <button ref={closeRef} type="button" className="btn btn-sm" onClick={close}><ArrowLeft size={12} />Return to investigation</button>
        <span className="kind">Spatial + biomechanical</span>
        <strong className="mono">{MATCH_ID}</strong>
        <span className="faint">{activeEvent ? `${activeEvent.event_id} · ${activeEvent.label} · ${activeEvent.start_s}–${activeEvent.end_s} s` : "full segment"}</span>
        <State>SYNTHETIC</State>
        <span className="spacer" />
        <label className="field"><span>Player</span>
          <select className="select" value={player} onChange={(event) => setPlayer(event.target.value)} aria-label="Selected player">
            {players.map((entity) => <option key={entity.player_id} value={entity.player_id}>{entity.player_id} · {entity.team}{match.data?.pose_athletes.includes(entity.player_id) ? " · pose" : ""}</option>)}
          </select>
        </label>
        <kbd>Esc</kbd>
      </header>
      <div className="viewer-body">
        {(match.isLoading || tracking.isLoading) && <Loading label="Loading bounded 10 Hz match segment" />}
        {(match.error || tracking.error) && <ErrorBox error={match.error ?? tracking.error} />}
        {frame && match.data && (
          <>
            <div className="match-grid">
              <div className="pitch-box">
                <span className="box-label">Field · 105 × 68 m · 1 unit = 10 m</span>
                <MatchPitch entities={frame.entities} poseJoints={poseFrame?.joints ?? []} selectedPlayer={player} onSelectPlayer={(id) => { setPlayer(id); setPlaying(false); }} />
                <div className="box-note">
                  <span><i className="swatch dot" style={{ background: "#4fc4b6" }} /> HOME</span>
                  <span><i className="swatch dot" style={{ background: "#e3a74e" }} /> AWAY</span>
                  <span><i className="swatch dot" style={{ background: "#f5f1dc" }} /> ball</span>
                  <span>click a player to select · drag to orbit · skeleton drawn 4× for visibility</span>
                </div>
              </div>
              <div className="pose-box">
                <span className="box-label">Pose · {player} · sagittal</span>
                {pose.isLoading && <div className="pose-unavailable">Loading pose stream</div>}
                {pose.data && !pose.data.available && (
                  <div className="pose-unavailable">
                    <State>UNAVAILABLE</State>
                    <span>{pose.data.message}</span>
                    <span className="faint small">Pose retained for:</span>
                    <div style={{ display: "flex", gap: 4, justifyContent: "center", flexWrap: "wrap" }}>{pose.data.pose_athletes.map((id) => <button key={id} type="button" className="chip" onClick={() => setPlayer(id)}>{id}</button>)}</div>
                  </div>
                )}
                {poseFrame && <PoseView joints={poseFrame.joints} athleteId={player} />}
                {poseFrame && <div className="box-note"><span className="mono">frame {poseFrame.frame} · t {poseFrame.time_s.toFixed(1)} s · {poseTimeMatches ? "synchronized with field" : "CLOCK MISMATCH"}</span></div>}
              </div>
              <div style={{ display: "grid", gap: 10, alignContent: "start" }}>
                <div className="frame">
                  <div className="frame-head"><h3>Derived at t = {frame.time_s.toFixed(1)} s</h3><State>DERIVED</State></div>
                  <div className="frame-body">
                    <KV rows={[
                      ["Speed", measures ? `${measures.speed.toFixed(2)} m·s⁻¹` : "—", "mono"],
                      ["Acceleration", measures?.acceleration !== null && measures?.acceleration !== undefined ? `${measures.acceleration.toFixed(2)} m·s⁻²` : "— (first frame)", "mono"],
                      ["Distance to ball", measures?.distanceToBall !== null && measures?.distanceToBall !== undefined ? `${measures.distanceToBall.toFixed(1)} m` : "—", "mono"],
                      ["Nearest opponent", measures?.nearestOpponent ? `${measures.nearestOpponent.id} · ${measures.nearestOpponent.distance.toFixed(1)} m` : "—", "mono"],
                      ["Event context", eventNow ? `${eventNow.event_id} ${eventNow.label}` : "outside annotated events"],
                    ]} />
                    <div className="note" style={{ marginTop: 6 }}><Info size={12} />Acceleration is the finite difference of tracking velocity between adjacent 10 Hz frames (unfiltered).</div>
                  </div>
                </div>
                <div className="frame">
                  <div className="frame-head"><h3>Joint-angle approximation</h3><State>{poseFrame ? "COMPUTED" : "UNAVAILABLE"}</State></div>
                  <div className="frame-body">
                    {angles ? (
                      <KV rows={[
                        ["Left knee", `${formatSig(angles.leftKnee, 3)}°`, "mono"],
                        ["Right knee", `${formatSig(angles.rightKnee, 3)}°`, "mono"],
                        ["Left hip", `${formatSig(angles.leftHip, 3)}°`, "mono"],
                        ["Right hip", `${formatSig(angles.rightHip, 3)}°`, "mono"],
                        ["Mean confidence", confidence === null ? "—" : `${(confidence * 100).toFixed(1)} %`, "mono"],
                      ]} />
                    ) : <div className="faint small">No pose stream for {player}; angles are not estimated.</div>}
                    <div className="note" style={{ marginTop: 6 }}><Info size={12} />3D geometric angle between adjacent segments of the synthetic pose stream; not a validated joint-kinematics model.</div>
                  </div>
                </div>
              </div>
            </div>
            <div className="timeline">
              <div className="timeline-top">
                <Button size="sm" variant="primary" onClick={() => { if (activeEvent && frameIndex >= Math.round(activeEvent.end_s * rate)) setFrameIndex(Math.round(activeEvent.start_s * rate)); setPlaying((value) => !value); }} aria-label={playing ? "Pause" : "Play"}>{playing ? <Pause size={12} /> : <Play size={12} />}{playing ? "Pause" : activeEvent ? "Play event" : "Play"}</Button>
                <Button size="sm" onClick={() => { setFrameIndex(activeEvent ? Math.round(activeEvent.start_s * rate) : 0); setPlaying(false); }}><SkipBack size={12} />{activeEvent ? "Event start" : "Start"}</Button>
                <span className="mono">{frame.time_s.toFixed(1)} s</span>
                <span className="faint mono small">frame {frameIndex} / {frames.length - 1} · {rate} Hz · segment {duration.toFixed(0)} s</span>
                <span style={{ flex: 1 }} />
                {events.map((event) => (
                  <button key={event.event_id} type="button" className="chip" aria-pressed={eventId === event.event_id} onClick={() => seekEvent(event)}>{event.event_id} {event.label} · {event.start_s}–{event.end_s} s</button>
                ))}
                {eventId && <button type="button" className="chip" onClick={() => { setEventId(undefined); wb.select({ matchEventId: null }); }}>full segment</button>}
              </div>
              <div className="timeline-track">
                <div className="timeline-rail" />
                <div className="timeline-fill" style={{ width: pct(frame.time_s) }} />
                {events.map((event) => (
                  <button key={event.event_id} type="button" className={`timeline-event ${eventId === event.event_id ? "active" : ""}`} style={{ left: pct(event.start_s), width: `calc(${pct(event.end_s)} - ${pct(event.start_s)})` }} title={`${event.label} ${event.start_s}–${event.end_s} s · ${event.athlete_id}`} onClick={() => seekEvent(event)} aria-label={`Seek to ${event.label}`} />
                ))}
                <div className="timeline-cursor" style={{ left: pct(frame.time_s) }} />
                <input type="range" min={0} max={frames.length - 1} value={frameIndex} onChange={(event) => { setFrameIndex(Number(event.target.value)); setPlaying(false); }} aria-label="Seek" />
              </div>
              <div className="timeline-ticks"><span>0 s</span><span>{(duration / 4).toFixed(0)} s</span><span>{(duration / 2).toFixed(0)} s</span><span>{((duration * 3) / 4).toFixed(0)} s</span><span>{duration.toFixed(0)} s</span></div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
