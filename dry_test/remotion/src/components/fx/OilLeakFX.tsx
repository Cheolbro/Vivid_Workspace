import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * OilLeakFX — 원유 유출 증발 파티클
 *
 * 부서진 콘크리트 탱크 틈새로 검은 원유 파티클이 공중으로 빠르게
 * 증발하듯 날아가는 극적인 유출 효과.
 *
 * 구조:
 *   ① 균열 지점 — 2~3개의 틈새 위치에서 파티클 폭발 방사
 *   ② 파티클 궤도 — 위로 솟구치며 좌우 확산, 가속 후 소멸
 *   ③ 증기 안개 — 균열 직상부에 흐릿한 안개구름
 *   ④ 주기 반복 — spring 초기 버스트 + 이후 루핑 방사
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: particleCount, crackCount, color, speed,
 *               spreadAngle, size, glowColor
 */

interface OilLeakFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number; // 화면 중심 기준 균열 중앙 X 오프셋
  y?: number; // 화면 중심 기준 균열 중앙 Y 오프셋
  particleCount?: number; // 파티클 총 수
  crackCount?: number; // 균열 지점 수 (1~4)
  color?: string; // 원유 색상 (기본: 흑갈색)
  speed?: number; // 상승 속도 배율
  spreadAngle?: number; // 좌우 확산 각도 (degree)
  size?: number; // 파티클 기본 크기 (px)
  glowColor?: string; // 유출 광채 색상 (기본: 짙은 황갈색)
}

// 결정론적 seed 난수
const sr = (seed: number, offset = 0): number => {
  const x = Math.sin(seed * 127.1 + offset * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// degree → radian
const deg2rad = (d: number) => (d * Math.PI) / 180;

export const OilLeakFX: React.FC<OilLeakFXProps> = ({
  startFrame = 0,
  durationFrames = 150,
  x = 0,
  y = 0,
  particleCount = 55,
  crackCount = 3,
  color = "#1A0800", // 짙은 흑갈색 원유
  speed = 5.5,
  spreadAngle = 70, // ±70° 범위로 상방 방사
  size = 8,
  glowColor = "#4A2A00", // 짙은 황갈색 광채
}) => {
  const frame = useCurrentFrame();
  const { fps, width: vw, height: vh } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // ── 전체 페이드인/아웃 ───────────────────────────────────────────
  const fadeIn = interpolate(rel, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(rel, [durationFrames - 12, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const globalOpacity = Math.min(fadeIn, fadeOut);

  // ── spring 초기 버스트 세기 (0프레임에서 폭발 시작) ─────────────
  const burstScale = spring({
    fps,
    frame: rel,
    config: { damping: 8, stiffness: 180, mass: 0.4 },
    durationInFrames: 20,
  });

  const cx = vw / 2 + x;
  const cy = vh / 2 + y;

  // ── 균열 지점 위치 정의 ─────────────────────────────────────────
  const cracks = Array.from({ length: crackCount }, (_, ci) => ({
    // 균열들을 수평으로 불균등 배치
    ox: (sr(ci, 10) - 0.5) * 260, // -130~+130px 분산
    oy: (sr(ci, 11) - 0.5) * 60, // ±30px 높낮이 변화
  }));

  // ── 파티클 생성 ─────────────────────────────────────────────────
  const particles = Array.from({ length: particleCount }, (_, i) => {
    // 어느 균열에서 나올지
    const crackIdx = i % crackCount;
    const crack = cracks[crackIdx];

    // 각 파티클의 고유 특성
    const lifespan = 0.35 + sr(i, 0) * 0.55; // 전체 duration 중 몇 배수 살아있는지
    const delay = sr(i, 1) * durationFrames * 0.65; // 발사 딜레이 (연속 방사)
    const localRel = rel - delay;
    if (localRel < 0) return null;

    const pLifeFrames = durationFrames * lifespan;
    if (localRel > pLifeFrames) return null;

    const progress = localRel / pLifeFrames; // 0~1

    // 발사 각도: 정수 위(270°)를 중심으로 ±spreadAngle
    const angleOffset = (sr(i, 2) - 0.5) * 2 * spreadAngle; // ±spreadAngle
    const angleDeg = -90 + angleOffset; // -90° = 정수 위
    const angleRad = deg2rad(angleDeg);

    // 속도: 각 파티클마다 변동
    const pSpeed = speed * (0.6 + sr(i, 3) * 1.0) * burstScale;

    // 위치 계산: 포물선 (X=cos, Y=sin → 위로 솟음)
    // progress^1.4 로 가속감 부여
    const dist = pSpeed * Math.pow(progress, 0.7) * 120;
    const px = crack.ox + Math.cos(angleRad) * dist;
    // 중력 효과: Y는 처음엔 빠르게 오르다 후반 약간 처짐
    const py = crack.oy + Math.sin(angleRad) * dist + 40 * Math.pow(progress, 2); // 중력

    // 파티클 크기: 시간이 지나며 부풀다 사라짐 (증발 느낌)
    const pSize = size * (0.4 + sr(i, 4) * 0.8) * (1 + progress * 1.8);

    // opacity: 등장 후 서서히 소멸 (연기처럼)
    const pOpacity = interpolate(progress, [0, 0.15, 0.7, 1.0], [0, 0.9, 0.55, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

    // 색상: 시작=짙은 흑갈 → 후반=반투명 연회색(증기)
    const smokeBlend = Math.pow(progress, 1.5);
    const r = Math.round(26 + smokeBlend * (160 - 26));
    const g = Math.round(8 + smokeBlend * (140 - 8));
    const b = Math.round(0 + smokeBlend * (130 - 0));
    const pColor = `rgb(${r},${g},${b})`;

    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: cx + px - pSize / 2,
          top: cy + py - pSize / 2,
          width: pSize,
          height: pSize,
          borderRadius: "50%",
          background: pColor,
          opacity: pOpacity,
          filter: `blur(${pSize * 0.22}px)`,
          boxShadow: progress < 0.3 ? `0 0 ${pSize}px ${pSize * 0.5}px ${glowColor}88` : "none",
        }}
      />
    );
  });

  // ── 균열 지점 증기 안개 ─────────────────────────────────────────
  const fogClouds = cracks.map((crack, ci) => {
    const fogOpacity = interpolate(
      rel,
      [0, 15, durationFrames - 10, durationFrames],
      [0, 0.45, 0.45, 0],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }
    );
    const fogPulse = 0.85 + Math.sin((rel / fps) * 3.2 + ci * 1.7) * 0.15;
    const fogW = 60 + sr(ci, 20) * 40;
    const fogH = 30 + sr(ci, 21) * 25;

    return (
      <div
        key={`fog-${ci}`}
        style={{
          position: "absolute",
          left: cx + crack.ox - fogW / 2,
          top: cy + crack.oy - fogH * 0.8,
          width: fogW,
          height: fogH,
          borderRadius: "50%",
          background: `radial-gradient(ellipse, ${glowColor}55 0%, transparent 70%)`,
          opacity: fogOpacity * fogPulse,
          filter: "blur(6px)",
        }}
      />
    );
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        opacity: globalOpacity,
        pointerEvents: "none",
      }}
    >
      {/* 균열 증기 안개 */}
      {fogClouds}
      {/* 원유 파티클 */}
      {particles}
    </div>
  );
};
