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

// CSS box-shadow 방식은 연산량이 너무 많아 폐기하고,
// 렌더링 최적화를 위해 SVG feTurbulence 필터(GPU 가속)로 대체합니다.

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
  const grainOpacity = noiseOpacity * preset.noise * envelope;

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
      {/* 레이어 1: Grain 노이즈 (SVG 필터 가속) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: grainOpacity,
          pointerEvents: "none",
          mixBlendMode: "overlay", // 필름 그레인 느낌을 위한 블렌드 모드
        }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="100%"
          height="100%"
          style={{ position: "absolute", inset: 0 }}
        >
          <filter id="grit-noise">
            {/* seed를 프레임에 연동해 끊임없이 움직이는 노이즈 생성 */}
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.75"
              numOctaves="2"
              stitchTiles="stitch"
              seed={Math.floor(rel * 0.5)}
            />
            {/* 노이즈를 흑백으로 변환 (흰색/검은색 노이즈) */}
            <feColorMatrix type="matrix" values="1 0 0 0 0, 1 0 0 0 0, 1 0 0 0 0, 0 0 0 1 0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#grit-noise)" />
        </svg>
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
