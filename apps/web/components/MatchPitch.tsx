"use client";

import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import type { MatchEntity, PoseJoint } from "@/lib/types";

/**
 * The pitch is rendered with 1 world unit = 10 m of the 105 x 68 m playing
 * surface, so the field, players, ball and pose skeleton all share one
 * coordinate frame. The skeleton is exaggerated by a documented factor so a
 * 1.8 m athlete stays visible at pitch scale; the exaggeration is disclosed in
 * the MatchLab legend rather than hidden.
 */
const METRES_PER_UNIT = 10;
const POSE_EXAGGERATION = 4;

export function fieldX(xMetres: number) {
  return (xMetres - 52.5) / METRES_PER_UNIT;
}

export function fieldZ(yMetres: number) {
  return (yMetres - 34) / METRES_PER_UNIT;
}

function Player({ entity, selected, onSelect }: { entity: MatchEntity; selected: boolean; onSelect: (id: string) => void }) {
  const color = entity.team === "HOME" ? "#59d6c7" : "#e5b567";
  return (
    <mesh position={[fieldX(entity.x_m), 0.18, fieldZ(entity.y_m)]} onClick={(event) => { event.stopPropagation(); onSelect(entity.player_id); }}>
      <sphereGeometry args={[selected ? 0.34 : 0.22, 16, 16]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? 0.85 : 0.25} roughness={0.38} metalness={0.18} />
    </mesh>
  );
}

function SelectedRing({ entity }: { entity: MatchEntity }) {
  const points = useMemo(() => {
    const segments = 40;
    const radius = 0.55;
    return Array.from({ length: segments + 1 }, (_, index) => {
      const angle = (index / segments) * Math.PI * 2;
      return [fieldX(entity.x_m) + Math.cos(angle) * radius, 0.02, fieldZ(entity.y_m) + Math.sin(angle) * radius] as [number, number, number];
    });
  }, [entity.x_m, entity.y_m]);
  return <Line points={points} color="#e8fffa" lineWidth={1.6} transparent opacity={0.9} />;
}

function PoseSkeleton({ joints }: { joints: PoseJoint[] }) {
  const lookup = useMemo(() => new Map(joints.map((joint) => [joint.joint, joint])), [joints]);
  const connections = [
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
  const anchor = lookup.get("hip");
  if (!anchor) return null;
  const scale = POSE_EXAGGERATION / METRES_PER_UNIT;
  const point = (joint: PoseJoint): [number, number, number] => [
    fieldX(anchor.x_m) + (joint.x_m - anchor.x_m) * scale,
    Math.max(0, joint.z_m) * scale,
    fieldZ(anchor.y_m) + (joint.y_m - anchor.y_m) * scale,
  ];
  const anchorPoint = point(anchor);
  return (
    <group>
      {connections.map(([from, to]) => {
        const a = lookup.get(from);
        const b = lookup.get(to);
        if (!a || !b) return null;
        return <Line key={`${from}-${to}`} points={[point(a), point(b)]} color="#b4e9e2" lineWidth={1.6} transparent opacity={0.92} />;
      })}
      {joints.map((joint) => (
        <mesh key={joint.joint} position={point(joint)}>
          <sphereGeometry args={[joint.confidence > 0.85 ? 0.055 : 0.035, 8, 8]} />
          <meshBasicMaterial color={joint.confidence > 0.85 ? "#e8fffa" : "#8fb8b3"} />
        </mesh>
      ))}
      <Line points={[anchorPoint, [anchorPoint[0], 0.02, anchorPoint[2]]]} color="#5f7d88" lineWidth={1} dashed dashSize={0.06} gapSize={0.05} transparent opacity={0.7} />
    </group>
  );
}

export default function MatchPitch({
  entities,
  poseJoints,
  selectedPlayer,
  onSelectPlayer,
}: {
  entities: MatchEntity[];
  poseJoints: PoseJoint[];
  selectedPlayer: string;
  onSelectPlayer: (id: string) => void;
}) {
  const players = entities.filter((entity) => entity.player_id !== "BALL");
  const ball = entities.find((entity) => entity.player_id === "BALL");
  const selected = players.find((entity) => entity.player_id === selectedPlayer);
  return (
    <Canvas camera={{ position: [0, 10.5, 12], fov: 42 }} dpr={[1, 1.5]} gl={{ antialias: true }}>
      <color attach="background" args={["#0b141b"]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[0, 8, 4]} intensity={1.6} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.03, 0]}>
        <planeGeometry args={[10.5, 6.8]} />
        <meshStandardMaterial color="#102b2c" roughness={0.95} />
      </mesh>
      <Line points={[[-5.25, 0, -3.4], [5.25, 0, -3.4], [5.25, 0, 3.4], [-5.25, 0, 3.4], [-5.25, 0, -3.4]]} color="#75a5a1" lineWidth={1} />
      <Line points={[[0, 0, -3.4], [0, 0, 3.4]]} color="#75a5a1" lineWidth={1} />
      <Line points={[[-5.25, 0, 0], [5.25, 0, 0]]} color="#75a5a1" lineWidth={1} />
      <Line points={[[-5.25, 0, -1.6], [-3.8, 0, -1.6], [-3.8, 0, 1.6], [-5.25, 0, 1.6]]} color="#75a5a1" lineWidth={1} />
      <Line points={[[5.25, 0, -1.6], [3.8, 0, -1.6], [3.8, 0, 1.6], [5.25, 0, 1.6]]} color="#75a5a1" lineWidth={1} />
      <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.35, 0.37, 32]} />
        <meshBasicMaterial color="#75a5a1" />
      </mesh>
      {players.map((entity) => (
        <Player key={entity.player_id} entity={entity} selected={entity.player_id === selectedPlayer} onSelect={onSelectPlayer} />
      ))}
      {selected && <SelectedRing entity={selected} />}
      {ball && (
        <mesh position={[fieldX(ball.x_m), 0.16, fieldZ(ball.y_m)]}>
          <sphereGeometry args={[0.12, 12, 12]} />
          <meshStandardMaterial color="#f5f1dc" emissive="#857b54" emissiveIntensity={0.3} />
        </mesh>
      )}
      {selected && poseJoints.length > 0 && <PoseSkeleton joints={poseJoints} />}
      <OrbitControls enablePan={false} minDistance={7} maxDistance={18} maxPolarAngle={Math.PI / 2.1} />
    </Canvas>
  );
}
