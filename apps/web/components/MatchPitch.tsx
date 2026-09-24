"use client";

import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import type { MatchEntity } from "@/lib/types";

interface PoseJoint { joint: string; x_m: number; y_m: number; z_m: number; confidence: number }

function fieldX(x: number) { return (x - 52.5) / 10; }
function fieldZ(y: number) { return (y - 34) / 10; }

function Player({ entity, selected, onSelect }: { entity: MatchEntity; selected: boolean; onSelect: (id: string) => void }) {
  const color = entity.team === "HOME" ? "#59d6c7" : "#e5b567";
  return <mesh position={[fieldX(entity.x_m), 0.18, fieldZ(entity.y_m)]} onClick={(event) => { event.stopPropagation(); onSelect(entity.player_id); }}>
    <sphereGeometry args={[selected ? 0.34 : 0.23, 16, 16]} />
    <meshStandardMaterial color={color} emissive={selected ? color : "#000000"} emissiveIntensity={selected ? 0.8 : 0.2} roughness={0.38} metalness={0.18} />
  </mesh>;
}

function PoseSkeleton({ joints }: { joints: PoseJoint[] }) {
  const lookup = useMemo(() => new Map(joints.map((joint) => [joint.joint, joint])), [joints]);
  const connections = [["hip", "left_hip"], ["hip", "right_hip"], ["hip", "knee"], ["knee", "ankle"], ["left_hip", "left_knee"], ["left_knee", "left_ankle"], ["right_hip", "right_knee"], ["right_knee", "right_ankle"], ["hip", "shoulder"], ["shoulder", "left_shoulder"], ["shoulder", "right_shoulder"], ["left_shoulder", "left_elbow"], ["left_elbow", "left_wrist"], ["right_shoulder", "right_elbow"], ["right_elbow", "right_wrist"]];
  const point = (joint: PoseJoint | undefined) => joint ? [joint.x_m * 0.7, joint.z_m * 1.7, joint.y_m * 0.7] as [number, number, number] : [0, 0, 0] as [number, number, number];
  return <group position={[0, 0.1, 0]}>{connections.map(([from, to]) => { const a = lookup.get(from); const b = lookup.get(to); if (!a || !b) return null; return <Line key={`${from}-${to}`} points={[point(a), point(b)]} color="#b4e9e2" lineWidth={1.4} transparent opacity={0.88} />; })}{joints.filter((joint) => ["hip", "knee", "ankle", "shoulder", "left_wrist", "right_wrist"].includes(joint.joint)).map((joint) => <mesh key={joint.joint} position={point(joint)}><sphereGeometry args={[0.07, 10, 10]} /><meshBasicMaterial color="#e8fffa" /></mesh>)}</group>;
}

export default function MatchPitch({ entities, poseJoints, selectedPlayer, onSelectPlayer }: { entities: MatchEntity[]; poseJoints: PoseJoint[]; selectedPlayer: string; onSelectPlayer: (id: string) => void }) {
  const players = entities.filter((entity) => entity.player_id !== "BALL");
  const ball = entities.find((entity) => entity.player_id === "BALL");
  return <Canvas camera={{ position: [0, 10.5, 12], fov: 42 }} dpr={[1, 1.5]} gl={{ antialias: true }}>
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
    <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.35, 0.37, 32]} /><meshBasicMaterial color="#75a5a1" /></mesh>
    {players.map((entity) => <Player key={entity.player_id} entity={entity} selected={entity.player_id === selectedPlayer} onSelect={onSelectPlayer} />)}
    {ball && <mesh position={[fieldX(ball.x_m), 0.16, fieldZ(ball.y_m)]}><sphereGeometry args={[0.12, 12, 12]} /><meshStandardMaterial color="#f5f1dc" emissive="#857b54" emissiveIntensity={0.3} /></mesh>}
    {poseJoints.length > 0 && <group position={[0, 0, 0]}><PoseSkeleton joints={poseJoints} /></group>}
    <OrbitControls enablePan={false} minDistance={7} maxDistance={18} maxPolarAngle={Math.PI / 2.1} />
  </Canvas>;
}
