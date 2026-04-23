import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * CloudDriftFX — 구름 천천히 흐르기 효과
 *
 * 원유 탱크·공장·항구 등 야외 산업 장면 위로 구름이 유유히 흘러가는
 * 배경 애니메이션. 장면에 시간의 흐름과 광활한 스케일을 부여합니다.
 *
 * · SVG ellipse 기반 결정론적(deterministic) 구름 생성 — 리렌더 안정.
 * · 각 구름 레이어는 서로 다른 속도·크기·투명도로 원근감(Parallax) 연출.
 * · direction: rightward(기본) / leftward 로 흐름 방향 반전 가능.
 * · cloudDensity: 0.0~1.0 — 구름 수 배율 조절.
 * · speed: 0.0~3.0 — 흐름 속도 배율 (0.8 기본, 느긋한 흐름).
 * · 등장/퇴장 부드러운 페이드 처리.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: intensity, cloudDensity, speed, direction,
 *                primaryColor, opacity, fadeInFrames
 */

type Direction = "rightward" | "leftward";
type Intensity = "low" | "medium" | "high";

interface CloudDriftFXProps {
  // commonProps
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  // specificProps
  intensity?: Intensity; // 구름 총 밀도/불투명도 프리셋 (기본 "medium")
  cloudDensity?: number; // 구름 수 배율 0.2~1.0 (기본 0.6)
  speed?: number; // 이동 속도 배율 px/frame (기본 0.8)
  direction?: Direction; // 흐름 방향 (기본 "rightward")
  primaryColor?: string; // 구름 기본 색상 (기본 "#FFFFFF")
  opacity?: number; // 전체 불투명도 0.0~1.0 (기본 0.72)
  fadeInFrames?: number; // 등장 페이드 구간 (기본 25프레임)
}

// intensity 프리셋 → opacity 배율
const INTENSITY_OPACITY: Record<Intensity, number> = {
  low: 0.55,
  medium: 0.72,
  high: 0.9,
};

// 결정론적 pseudo-random (seed 기반)
const pseudoRand = (seed: number, offset = 0): number => {
  const x = Math.sin(seed * 127.1 + offset * 311.7) * 43758.5453;
  return x - Math.floor(x); // 0~1
};

// 구름 하나: 여러 ellipse 덩어리를 겹쳐서 뭉게구름 형태 연출
const drawCloud = (
  cx: number,
  cy: number,
  scale: number,
  color: string,
  alpha: number,
  key: string
) => {
  const bumps = [
    { rx: 90 * scale, ry: 54 * scale, dx: 0, dy: 0 },
    { rx: 70 * scale, ry: 45 * scale, dx: -75 * scale, dy: 18 * scale },
    { rx: 60 * scale, ry: 42 * scale, dx: 80 * scale, dy: 14 * scale },
    { rx: 50 * scale, ry: 36 * scale, dx: -40 * scale, dy: -36 * scale },
    { rx: 45 * scale, ry: 32 * scale, dx: 50 * scale, dy: -28 * scale },
  ];

  return (
    <g key={key} opacity={alpha}>
      {bumps.map((b, i) => (
        <ellipse key={i} cx={cx + b.dx} cy={cy + b.dy} rx={b.rx} ry={b.ry} fill={color} />
      ))}
    </g>
  );
};

export const CloudDriftFX: React.FC<CloudDriftFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  intensity = "medium",
  cloudDensity = 0.6,
  speed = 0.8,
  direction = "rightward",
  primaryColor = "#FFFFFF",
  opacity = 0.72,
  fadeInFrames = 25,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 등장 페이드인
  const fadeIn = interpolate(rel, [0, fadeInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃 (마지막 20프레임)
  const fadeOut = interpolate(rel, [durationFrames - 20, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const baseOpacity = INTENSITY_OPACITY[intensity];
  const globalOpacity = Math.max(opacity, baseOpacity) * 0.5 + Math.min(opacity, baseOpacity) * 0.5;
  const finalOpacity = globalOpacity * Math.min(fadeIn, fadeOut);

  // 구름 수: 기본 6개 × cloudDensity
  const baseCount = 6;
  const cloudCount = Math.max(2, Math.round(baseCount * cloudDensity));

  // 이동 방향: rightward = +, leftward = -
  const sign = direction === "rightward" ? 1 : -1;

  const clouds = Array.from({ length: cloudCount }, (_, i) => {
    // 각 구름의 고정 속성
    const scale = 0.5 + pseudoRand(i, 0) * 1.2; // 0.5~1.7
    const baseX = pseudoRand(i, 1) * width; // 초기 X (화면 내)
    const baseY = pseudoRand(i, 2) * (height * 0.55); // 위쪽 55% 영역
    const speedMult = 0.5 + pseudoRand(i, 3) * 1.0; // 속도 개별 변동 (0.5~1.5)
    const alphaVar = 0.55 + pseudoRand(i, 4) * 0.45; // 개별 투명도 (0.55~1.0)

    // 이동: 화면 가로 + 구름 최대 반경(약 200px) 범위에서 wrap
    const totalWidth = width + 400;
    const offset = rel * speed * speedMult * sign;
    const rawX = baseX + offset;
    // wrap: rightward → 오른쪽으로 나가면 왼쪽에서 재등장
    const wrappedX =
      direction === "rightward"
        ? (((rawX % totalWidth) + totalWidth) % totalWidth) - 200
        : (((-rawX % totalWidth) + totalWidth) % totalWidth) - 200;

    return drawCloud(wrappedX, baseY, scale, primaryColor, alphaVar, `cloud_${i}`);
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        transform: `translate(${x}px, ${y}px)`,
        opacity: finalOpacity,
        pointerEvents: "none",
        overflow: "hidden",
      }}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        xmlns="http://www.w3.org/2000/svg"
        style={{ position: "absolute", inset: 0 }}
      >
        {/* 구름에 은은한 blur 필터 적용 — 부드러운 뭉게구름 질감 */}
        <defs>
          <filter id="cloudBlur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>
        <g filter="url(#cloudBlur)">{clouds}</g>
      </svg>
    </div>
  );
};
