import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * OilFillFX — 원유 차오름 + 홀로그램 파티클
 *
 * 거대한 석유 탱크 내부에 검은 황금(원유)이 서서히 가득 차오르며
 * 든든함과 풍요를 상징하는 빛나는 홀로그램 파티클 연출.
 *
 * 구조:
 *   ① 원유 액체층 — 아래에서 위로 easeInOut 상승
 *   ② 유면(油面) 경계 광채 — sin 파형 shimmer
 *   ③ 홀로그램 파티클 — 액체 위를 부유하며 금빛/청록빛으로 반짝임
 *   ④ 전체 페이드인/아웃
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: fillColor, glowColor, particleCount, width, height, fillSpeed
 */

interface OilFillFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  fillColor?: string; // 원유 색상 (기본: 짙은 흑갈색)
  glowColor?: string; // 홀로그램 광채 색상 (기본: 황금)
  particleCount?: number; // 부유 파티클 수
  width?: number; // 탱크 표시 너비 (px)
  height?: number; // 탱크 표시 높이 (px)
  fillSpeed?: number; // 0~1: 1에 가까울수록 일찍 꽉 참 (기본 0.75)
}

// 결정론적 seed 난수 (리렌더 안정)
const sr = (seed: number, offset = 0): number => {
  const x = Math.sin(seed * 91.3 + offset * 217.9) * 43758.5453;
  return x - Math.floor(x);
};

export const OilFillFX: React.FC<OilFillFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  fillColor = "#1A0F00", // 짙은 흑갈색 원유
  glowColor = "#FFD700", // 황금빛 홀로그램
  particleCount = 28,
  width = 480,
  height = 320,
  fillSpeed = 0.75,
}) => {
  const frame = useCurrentFrame();
  const { fps, width: vw, height: vh } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // ── 전체 페이드인/아웃 ───────────────────────────────────────────
  const fadeIn = interpolate(rel, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const globalOpacity = Math.min(fadeIn, fadeOut);

  // ── ① 원유 액체층: 아래에서 위로 차오름 ─────────────────────────
  const fillEnd = Math.round(durationFrames * fillSpeed);
  const fillFraction = interpolate(rel, [0, fillEnd], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  const liquidHeight = fillFraction * height;
  const liquidTop = height - liquidHeight; // 컨테이너 내 유면 Y 위치

  // ── ② 유면 shimmer: sin 파형으로 물결 흔들림 ────────────────────
  const shimmerPhase = (rel / fps) * Math.PI * 2 * 1.2;
  const shimmerY = Math.sin(shimmerPhase) * 5; // ±5px
  const shimmerOpacity = 0.5 + Math.sin(shimmerPhase * 0.7) * 0.3;

  // ── ③ 홀로그램 파티클: 유면 위 부유 ─────────────────────────────
  const particles = Array.from({ length: particleCount }, (_, i) => {
    const px = sr(i, 0) * width;
    const baseRelY = sr(i, 1) * 0.55; // 유면에서 위로 0~55% 범위
    const floatAmp = 8 + sr(i, 2) * 14;
    const floatHz = 0.8 + sr(i, 3) * 1.2;
    const phase = sr(i, 4) * Math.PI * 2;
    const size = 3 + sr(i, 5) * 7;

    // 황금 ↔ 청록 컬러 사이클
    const hueShift = Math.sin(rel * 0.06 + phase) * 0.5 + 0.5;
    const pColor = hueShift > 0.5 ? glowColor : "#00FFD4";

    const floatY = Math.sin((rel / fps) * floatHz * Math.PI * 2 + phase) * floatAmp;
    const py = liquidTop + shimmerY - baseRelY * Math.max(liquidHeight, 1) - floatAmp + floatY;

    // 파티클이 컨테이너 아래(아직 액체 없음) 또는 위 경계 밖이면 숨김
    if (py > height || py < -size) return null;

    const pOpacity =
      fillFraction > 0.04
        ? interpolate(rel, [0, 20], [0, 0.65 + sr(i, 6) * 0.35], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        : 0;

    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: px - size / 2,
          top: py - size / 2,
          width: size,
          height: size,
          borderRadius: "50%",
          background: pColor,
          opacity: pOpacity,
          boxShadow: `0 0 ${size * 1.6}px ${size * 0.9}px ${pColor}55`,
          filter: `blur(${size * 0.12}px)`,
        }}
      />
    );
  });

  const cx = vw / 2 + x;
  const cy = vh / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx - width / 2,
        top: cy - height / 2,
        width,
        height,
        opacity: globalOpacity,
        pointerEvents: "none",
        overflow: "hidden",
        borderRadius: "8px",
      }}
    >
      {/* ① 원유 액체층 */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "100%",
          height: `${liquidHeight}px`,
          background: `linear-gradient(to top, ${fillColor} 55%, #2E1200 85%, #3D1A00 100%)`,
        }}
      />

      {/* ② 유면 shimmer 경계선 */}
      {liquidHeight > 4 && (
        <div
          style={{
            position: "absolute",
            bottom: liquidHeight + shimmerY - 3,
            left: 0,
            width: "100%",
            height: "7px",
            background: `linear-gradient(to right,
              transparent 0%,
              ${glowColor}99 25%,
              #00FFD488 50%,
              ${glowColor}99 75%,
              transparent 100%)`,
            opacity: shimmerOpacity,
            filter: "blur(2px)",
          }}
        />
      )}

      {/* 유면 위 홀로그램 안개 */}
      {liquidHeight > 12 && (
        <div
          style={{
            position: "absolute",
            bottom: liquidHeight + shimmerY,
            left: 0,
            width: "100%",
            height: Math.min(liquidHeight * 0.4, 90),
            background: `linear-gradient(to top, ${glowColor}28, transparent)`,
            opacity: 0.55 + shimmerOpacity * 0.45,
          }}
        />
      )}

      {/* ③ 홀로그램 파티클 */}
      {particles}
    </div>
  );
};
