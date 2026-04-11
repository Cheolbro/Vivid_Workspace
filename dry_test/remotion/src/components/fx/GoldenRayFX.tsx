/**
 * GoldenRayFX.tsx
 * 창고 안의 쌀가마니 위로 은은한 황금빛 빛줄기가 떨어지며
 * 가치를 부여하는 파티클 효과.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: rayCount, particleCount, color, glowColor, spreadWidth
 */

import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, random } from "remotion";

// ── Props 타입 ────────────────────────────────────────────────────────────────

interface CommonProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number; // 중심 X 오프셋 (px, 0 = 화면 중앙)
  y?: number; // 중심 Y 오프셋 (px, 0 = 화면 중앙)
}

interface SpecificProps {
  rayCount?: number; // 빛줄기 개수 (기본 8)
  particleCount?: number; // 먼지/파티클 개수 (기본 40)
  color?: string; // 빛줄기 색상 (기본 황금색)
  glowColor?: string; // 발광 후광 색상
  spreadWidth?: number; // 빛줄기 퍼짐 폭 (px, 기본 320)
}

type Props = CommonProps & SpecificProps;

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export const GoldenRayFX: React.FC<Props> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 60,
  rayCount = 8,
  particleCount = 40,
  color = "#FFD700",
  glowColor = "#FFF0A0",
  spreadWidth = 320,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 전체 페이드인/페이드아웃
  const masterOpacity = interpolate(
    rel,
    [0, 12, durationFrames - 16, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // 빛줄기 길이 (처음에 짧다가 길어짐)
  const rayGrow = interpolate(rel, [0, 30], [0.1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // ── 빛줄기 렌더 ───────────────────────────────────────────
  const rays = Array.from({ length: rayCount }, (_, i) => {
    const seed = i * 137.5;
    const angle = (i / rayCount) * 180 + 270; // 아래 방향 ±90° 범위 (위에서 내려오는 fan)
    const fanAngle = ((i / (rayCount - 1) - 0.5) * spreadWidth) / 3; // ±spread/6 deg
    const finalAngle = angle + fanAngle;
    const rad = (finalAngle * Math.PI) / 180;
    const rayLen = (random(seed) * 0.3 + 0.7) * height * 0.55 * rayGrow;
    const w = random(seed + 1) * 14 + 6;
    const alpha = (random(seed + 2) * 0.35 + 0.25) * masterOpacity;

    const x2 = cx + Math.cos(rad) * rayLen;
    const y2 = cy + Math.sin(rad) * rayLen;

    // 빛줄기 진동 (느린 흔들림)
    const wobble = Math.sin((rel / durationFrames) * Math.PI * 2 + seed) * 6;

    return (
      <line
        key={i}
        x1={cx}
        y1={cy}
        x2={x2 + wobble}
        y2={y2}
        stroke={color}
        strokeWidth={w}
        strokeLinecap="round"
        opacity={alpha}
        style={{ filter: `blur(${w * 0.6}px)` }}
      />
    );
  });

  // ── 먼지 파티클 렌더 ──────────────────────────────────────
  const particles = Array.from({ length: particleCount }, (_, i) => {
    const seed = i * 73 + 500;
    const lifeStart = random(seed) * (durationFrames * 0.5);
    const lifeLen = random(seed + 1) * (durationFrames * 0.4) + durationFrames * 0.15;
    const lifeRel = rel - lifeStart;

    if (lifeRel < 0 || lifeRel > lifeLen) return null;

    const progress = lifeRel / lifeLen;
    const pAlpha =
      interpolate(progress, [0, 0.15, 0.8, 1], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }) * masterOpacity;

    // 파티클 궤도: 위에서 아래로 떨어짐 + 좌우 드리프트
    const startX = cx + (random(seed + 2) - 0.5) * spreadWidth;
    const startY = cy - height * (random(seed + 3) * 0.25 + 0.05);
    const driftX = (random(seed + 4) - 0.5) * 60;
    const fallY = height * (random(seed + 5) * 0.2 + 0.1);

    const px = startX + driftX * progress;
    const py = startY + fallY * progress;
    const radius = random(seed + 6) * 4 + 2;

    return (
      <circle
        key={i}
        cx={px}
        cy={py}
        r={radius}
        fill={glowColor}
        opacity={pAlpha}
        style={{ filter: `blur(${radius * 0.8}px)` }}
      />
    );
  });

  // ── 중심 발광 후광 ────────────────────────────────────────
  const glowPulse = 0.6 + Math.sin((rel / durationFrames) * Math.PI * 4) * 0.2;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        opacity: masterOpacity,
      }}
    >
      <svg
        width={width}
        height={height}
        style={{ position: "absolute", inset: 0, overflow: "visible" }}
      >
        {/* 중심 발광 후광 */}
        <radialGradient id="goldenGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={glowColor} stopOpacity={0.7 * glowPulse} />
          <stop offset="60%" stopColor={color} stopOpacity={0.2 * glowPulse} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </radialGradient>
        <ellipse cx={cx} cy={cy} rx={180 * glowPulse} ry={80 * glowPulse} fill="url(#goldenGlow)" />

        {/* 빛줄기 */}
        {rays}

        {/* 파티클 */}
        {particles}
      </svg>
    </div>
  );
};
