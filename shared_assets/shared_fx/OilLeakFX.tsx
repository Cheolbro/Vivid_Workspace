import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * OilLeakFX — 허공의 원형 구멍에서 검은 물줄기가 우측으로 뿜어져 나와 아래로 떨어지며 바닥에 고이는 효과
 */

interface OilLeakFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number; // 구멍 X 위치 (화면 중심 기준)
  y?: number; // 구멍 Y 위치 (화면 중심 기준)
  particleCount?: number; // (하위 호환 유지) 흐름을 강조하는 물방울 디테일 개수
  color?: string; // 원유 색상
  vx?: number; // 초기 우측 수평 속도
  gravity?: number; // 중력 가속도
  floorY?: number; // 바닥 Y 위치 (구멍 기준 상대적 높이)
  size?: number; // 물줄기 두께
  glowColor?: string; // 구멍 및 액체 광채
}

export const OilLeakFX: React.FC<OilLeakFXProps> = ({
  startFrame = 0,
  durationFrames = 150,
  x = 0,
  y = 0,
  particleCount = 60,
  color = "#050200",
  vx = 10.0,
  gravity = 0.4,
  floorY = 400,
  size = 18,
  glowColor = "#1A0A00",
}) => {
  const frame = useCurrentFrame();
  const { width: vw, height: vh, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const fadeIn = interpolate(rel, [0, 10], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
  });
  const globalOpacity = Math.min(fadeIn, fadeOut);

  const cx = vw / 2 + x;
  const cy = vh / 2 + y;

  // y = 0.5 * g * t^2 에 따라 바닥에 닿는 시간(프레임) 계산
  const reachTime = Math.sqrt((2 * floorY) / gravity);
  const reachX = vx * reachTime;

  // 물줄기 애니메이션 진행도 (0~1)
  const streamProgress = interpolate(rel, [5, 5 + reachTime], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.4, 0, 0.2, 1),
  });

  // 바닥 웅덩이(Puddle) 크기 확장
  const puddleStartFrame = 5 + reachTime;
  const puddleScale = interpolate(rel, [puddleStartFrame, puddleStartFrame + 30], [0, 1.5], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  // 유출 구멍 크기 (스프링)
  const holeScale = spring({
    fps,
    frame: rel,
    config: { damping: 14, stiffness: 100 },
  });

  // 물줄기 경로 (Cubic Bezier: 수평으로 시작해 중력으로 꺾이는 포물선 모사)
  // M 0 0: 구멍 중심에서 시작
  const pathData = `M 0 0 C ${reachX * 0.4} 0 ${reachX * 0.75} ${floorY * 0.2} ${reachX} ${floorY}`;
  const pathLength = 2500; // 충분히 긴 길이값

  // 잔여 물방울 (흐르는 느낌 강조)
  const dripsCount = Math.min(particleCount, 15);
  const drips = Array.from({ length: dripsCount }).map((_, i) => {
    const delay = i * 6;
    const dripRel = rel - 5 - delay;
    if (dripRel < 0) return null;

    // t는 물방울이 경로를 따라 이동하는 진행도
    const t = interpolate(dripRel, [0, reachTime], [0, 1], { extrapolateRight: "clamp" });
    if (t >= 1) return null; // 바닥에 닿으면 소멸 (웅덩이에 흡수)

    // Bezier 곡선 상의 좌표 계산
    const p0 = { x: 0, y: 0 };
    const p1 = { x: reachX * 0.4, y: 0 };
    const p2 = { x: reachX * 0.75, y: floorY * 0.2 };
    const p3 = { x: reachX, y: floorY };

    const dx =
      Math.pow(1 - t, 3) * p0.x +
      3 * Math.pow(1 - t, 2) * t * p1.x +
      3 * (1 - t) * Math.pow(t, 2) * p2.x +
      Math.pow(t, 3) * p3.x;
    const dy =
      Math.pow(1 - t, 3) * p0.y +
      3 * Math.pow(1 - t, 2) * t * p1.y +
      3 * (1 - t) * Math.pow(t, 2) * p2.y +
      Math.pow(t, 3) * p3.y;

    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: dx,
          top: dy,
          width: size * 0.8,
          height: size * 1.2,
          background: glowColor,
          borderRadius: "50%",
          opacity: 0.6 * (1 - t), // 떨어질수록 흐려짐
          transform: `translate(-50%, -50%) rotate(${Math.atan2(dy, dx) * (180 / Math.PI)}deg)`,
        }}
      />
    );
  });

  return (
    <div style={{ position: "absolute", inset: 0, opacity: globalOpacity, pointerEvents: "none" }}>
      {/* 바닥 웅덩이 */}
      <div
        style={{
          position: "absolute",
          left: cx + reachX,
          top: cy + floorY,
          width: size * 10 * puddleScale,
          height: size * 3 * puddleScale,
          background: color,
          borderRadius: "50%",
          transform: "translate(-50%, -50%)",
          filter: `blur(${size * 0.3}px)`,
          boxShadow: `0 0 ${size * 2}px ${glowColor}aa`,
          opacity: puddleScale > 0 ? 0.95 : 0,
        }}
      />

      {/* 물줄기 SVG 컨테이너 */}
      <svg
        style={{
          position: "absolute",
          left: cx,
          top: cy,
          width: 1,
          height: 1,
          overflow: "visible",
        }}
      >
        <defs>
          <filter id="oilGlow">
            <feGaussianBlur in="SourceGraphic" stdDeviation={size * 0.15} result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* 메인 물줄기 경로 (처음에 주욱 늘어나며 등장) */}
        {streamProgress > 0 && (
          <path
            d={pathData}
            fill="none"
            stroke={color}
            strokeWidth={size}
            strokeLinecap="round"
            filter="url(#oilGlow)"
            style={{
              strokeDasharray: pathLength,
              strokeDashoffset: pathLength * (1 - streamProgress),
            }}
          />
        )}
      </svg>

      {/* 흐르는 물방울 디테일 (SVG와 별개로 div로 구현하여 광원 효과) */}
      <div style={{ position: "absolute", left: cx, top: cy, overflow: "visible" }}>{drips}</div>

      {/* 원유 유출 구멍 */}
      <div
        style={{
          position: "absolute",
          left: cx,
          top: cy,
          width: size * 2.5 * holeScale,
          height: size * 2.5 * holeScale,
          background: "black",
          borderRadius: "50%",
          transform: "translate(-50%, -50%)",
          boxShadow: `inset 0 0 ${size * 0.8}px ${glowColor}, 0 0 ${size * 1.5}px ${glowColor}aa`,
          border: `2px solid ${glowColor}88`,
        }}
      />
    </div>
  );
};
