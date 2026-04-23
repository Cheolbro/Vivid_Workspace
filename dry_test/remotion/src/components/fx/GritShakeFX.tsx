import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * GritShakeFX — 거친 텍스처 + 카메라 흔들림 위기감 효과
 *
 * 충격적인 사건·위기 장면에서 화면 전체에 위기감을 고조시킵니다.
 *
 * [레이어 구성]
 * 1. 카메라 Shake  : sin 복합파로 x/y 흔들림 → 전체 컨테이너에 transform 적용
 * 2. Grain 노이즈  : CSS box-shadow 격자 기반 정적 노이즈 (Remotion SSR 안전)
 * 3. Vignette 오버레이: 외곽 어두운 방사형 그라디언트
 * 4. Color Tint   : primaryColor 반투명 오버레이 (붉은 기운)
 *
 * · intensity 프리셋으로 shakeAmplitude·noiseOpacity·vignetteIntensity 일괄 조절.
 * · 각 prop을 직접 지정하면 intensity 프리셋 대비 세밀 조정 가능.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: intensity, shakeAmplitude, noiseOpacity,
 *                vignetteIntensity, primaryColor, fadeInFrames
 */

type Intensity = "low" | "medium" | "high";

interface GritShakeFXProps {
  // commonProps
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  // specificProps
  intensity?: Intensity; // 전체 강도 프리셋 low/medium/high (기본 "high")
  shakeAmplitude?: number; // 흔들림 최대 진폭 px (기본 5)
  noiseOpacity?: number; // 그레인 노이즈 투명도 0.0~1.0 (기본 0.15)
  vignetteIntensity?: number; // 비네팅 강도 0.0~1.0 (기본 0.6)
  primaryColor?: string; // 컬러 틴트 (기본 "#FF0000")
  fadeInFrames?: number; // 등장 페이드 구간 (기본 8프레임, 빠르게 시작)
}

// intensity 프리셋 배율 테이블
const PRESET: Record<Intensity, { shake: number; noise: number; vignette: number }> = {
  low: { shake: 0.5, noise: 0.6, vignette: 0.6 },
  medium: { shake: 0.8, noise: 0.85, vignette: 0.85 },
  high: { shake: 1.0, noise: 1.0, vignette: 1.0 },
};

// 결정론적 pseudo-random
const pseudoRand = (seed: number, offset = 0): number => {
  const x = Math.sin(seed * 127.1 + offset * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

// CSS box-shadow 격자 노이즈 생성 (경량, SSR 안전)
// cols × rows 개의 dot을 box-shadow로 표현
const buildGrainShadow = (
  cols: number,
  rows: number,
  dotSize: number,
  frame: number,
  color: string
): string => {
  const shadows: string[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // frame을 seed에 혼합해 매 프레임 다른 노이즈 패턴 생성
      const val = pseudoRand(r * 200 + c, frame * 0.137);
      if (val > 0.62) {
        // 약 38% dot 밀도
        const x = c * dotSize;
        const y = r * dotSize;
        const alpha = Math.round(((val - 0.62) / 0.38) * 255)
          .toString(16)
          .padStart(2, "0");
        shadows.push(`${x}px ${y}px 0 ${color}${alpha}`);
      }
    }
  }
  return shadows.join(", ") || "none";
};

export const GritShakeFX: React.FC<GritShakeFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  intensity = "high",
  shakeAmplitude = 5,
  noiseOpacity = 0.15,
  vignetteIntensity = 0.6,
  primaryColor = "#FF0000",
  fadeInFrames = 8,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const preset = PRESET[intensity];

  // 등장 페이드인 (빠르게: 8프레임)
  const fadeIn = interpolate(rel, [0, fadeInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃 (마지막 15프레임)
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const envelope = Math.min(fadeIn, fadeOut);

  // ── 1. 카메라 Shake ──────────────────────────────────────────────
  // 복합 sin 파로 불규칙한 흔들림 연출 (주파수 3개 혼합)
  const t = rel / fps;
  const amp = shakeAmplitude * preset.shake * envelope;

  const shakeX =
    amp * (Math.sin(t * 23.4) * 0.5 + Math.sin(t * 37.8) * 0.3 + Math.sin(t * 61.2) * 0.2);
  const shakeY =
    amp * (Math.sin(t * 19.7) * 0.5 + Math.sin(t * 43.1) * 0.3 + Math.sin(t * 71.5) * 0.2);

  // ── 2. Grain 노이즈 파라미터 ────────────────────────────────────
  const dotSize = 4; // 노이즈 dot 1개 크기(px)
  const cols = Math.ceil(width / dotSize);
  const rows = Math.ceil(height / dotSize);
  const grainOpacity = noiseOpacity * preset.noise * envelope;

  // box-shadow 노이즈는 매 프레임 재계산 (결정론적)
  const grainShadow = buildGrainShadow(cols, rows, dotSize, rel, "#FFFFFF");

  // ── 3. Vignette 설정 ────────────────────────────────────────────
  const vigOpacity = vignetteIntensity * preset.vignette * envelope;

  // ── 4. Color Tint 설정 ──────────────────────────────────────────
  const hex = primaryColor.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const tintOpacity = 0.06 * preset.noise * envelope; // 매우 은은하게

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        pointerEvents: "none",
        // 전체 컨테이너에 카메라 흔들림 적용
        transform: `translate(${x + shakeX}px, ${y + shakeY}px)`,
        // 흔들림으로 약간 잘릴 수 있으므로 overflow 숨김
        overflow: "hidden",
      }}
    >
      {/* 레이어 1: Grain 노이즈 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: grainOpacity,
          pointerEvents: "none",
        }}
      >
        {/* box-shadow dot 기법: 1px 기준 div에서 box-shadow로 격자 노이즈 확장 */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: dotSize,
            height: dotSize,
            background: "transparent",
            boxShadow: grainShadow,
          }}
        />
      </div>

      {/* 레이어 2: Vignette */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: vigOpacity,
          pointerEvents: "none",
          background: [
            "radial-gradient(ellipse at center,",
            "  rgba(0,0,0,0) 38%,",
            "  rgba(0,0,0,0.55) 68%,",
            "  rgba(0,0,0,0.92) 100%",
            ")",
          ].join(" "),
        }}
      />

      {/* 레이어 3: Color Tint (붉은 기운) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: tintOpacity,
          pointerEvents: "none",
          background: `rgba(${r},${g},${b}, 0.85)`,
        }}
      />
    </div>
  );
};
