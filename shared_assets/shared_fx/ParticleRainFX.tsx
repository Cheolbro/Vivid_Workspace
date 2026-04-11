import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * ParticleRainFX — 파티클 하강 효과
 *
 * 폭락하는 주가(붉은 비), 쏟아지는 보조금(황금 비) 등
 * 화면 전체를 가로지르는 거대한 흐름을 시각화합니다.
 * useCurrentFrame + 인덱스 시드로 완전 결정론적(deterministic) 계산 — 리렌더 안정.
 *
 * commonProps  : startFrame, durationFrames (x, y 미사용)
 * specificProps: particleCount, color, speed, size, shape, opacity
 */

interface ParticleRainFXProps {
  startFrame?: number;
  durationFrames?: number;
  particleCount?: number; // 파티클 수 (기본 40)
  color?: string; // 파티클 색상 (기본: 황금)
  speed?: number; // 낙하 속도 배율 (기본 4.0)
  size?: number; // 파티클 크기 px (기본 10)
  shape?: "circle" | "square"; // 파티클 모양 (기본: circle)
  opacity?: number; // 전체 투명도 0~1 (기본 0.75)
}

// 결정론적 pseudo-random: 인덱스 기반 시드
const pseudoRand = (seed: number, offset = 0) => {
  const x = Math.sin(seed * 127.1 + offset * 311.7) * 43758.5453;
  return x - Math.floor(x); // 0~1
};

export const ParticleRainFX: React.FC<ParticleRainFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  particleCount = 40,
  color = "#FFD700",
  speed = 4.0,
  size = 10,
  shape = "circle",
  opacity = 0.75,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 전체 페이드인 (12프레임) / 페이드아웃 (15프레임)
  const fadeIn = interpolate(rel, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const globalOpacity = opacity * Math.min(fadeIn, fadeOut);

  const particles = Array.from({ length: particleCount }, (_, i) => {
    // 각 파티클의 고유 시드 값
    const xRatio = pseudoRand(i, 0); // X 위치 (0~1)
    const startFrac = pseudoRand(i, 1); // 시작 위치 오프셋 (0~1)
    const speedMult = 0.6 + pseudoRand(i, 2) * 0.8; // 속도 개별 변동 (0.6~1.4)
    const sizeVar = 0.6 + pseudoRand(i, 3) * 0.8; // 크기 개별 변동
    const opVar = 0.5 + pseudoRand(i, 4) * 0.5; // 불투명도 개별 변동

    const pxSize = size * sizeVar;

    // 낙하 Y: rel * speed * speedMult 로 계산, height + size 초과 시 화면 위로 wrap
    const totalTravel = height + pxSize * 2;
    const startY = -pxSize + startFrac * totalTravel; // 초기 위치 (화면 위 ~ 화면 내)
    const rawY = startY + rel * speed * speedMult;
    const yPos = (((rawY % totalTravel) + totalTravel) % totalTravel) - pxSize;

    const xPos = xRatio * (width - pxSize);

    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: xPos,
          top: yPos,
          width: pxSize,
          height: pxSize,
          background: color,
          borderRadius: shape === "circle" ? "50%" : "2px",
          opacity: opVar,
          boxShadow: `0 0 ${pxSize * 0.6}px ${color}88`,
        }}
      />
    );
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        opacity: globalOpacity,
        pointerEvents: "none",
        overflow: "hidden",
      }}
    >
      {particles}
    </div>
  );
};
