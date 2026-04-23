import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * BottomShadowFX — 하단 안정감 그림자 강조 효과
 *
 * 쌀가마니·상품 창고 등 하단에 무게감 있는 피사체가 쌓인 장면에서
 * 화면 하단부에 은은하고 안정적인 그라디언트 그림자를 드리워
 * 시청자에게 "묵직하게 쌓인" 안도감·신뢰감을 전달합니다.
 *
 * · upward: 화면 하단 → 상단 방향으로 그라디언트 (기본, 쌀가마니 장면)
 * · downward: 화면 상단 → 하단 방향 (빛이 위에서 비추는 장면)
 * · 부드러운 등장(fadeInFrames) / 퇴장(마지막 15f) 페이드 처리
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: primaryColor, intensity, opacity,
 *                gradientHeight, direction, fadeInFrames
 */

type Direction = "upward" | "downward";
type Intensity = "low" | "medium" | "high";

interface BottomShadowFXProps {
  // commonProps
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  // specificProps
  primaryColor?: string; // 그림자 색상 (기본: #000000)
  intensity?: Intensity; // low/medium/high — opacity 배율 프리셋
  opacity?: number; // 최대 불투명도 0.0~1.0 (기본 0.45)
  gradientHeight?: string; // 그라디언트 높이 (기본 "350px")
  direction?: Direction; // 그라디언트 방향 (기본 "upward")
  fadeInFrames?: number; // 등장 페이드 구간 (기본 20프레임)
}

// intensity 프리셋 → opacity 배율
const INTENSITY_MULTIPLIER: Record<Intensity, number> = {
  low: 0.7,
  medium: 1.0,
  high: 1.4,
};

export const BottomShadowFX: React.FC<BottomShadowFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  primaryColor = "#000000",
  intensity = "low",
  opacity = 0.45,
  gradientHeight = "350px",
  direction = "upward",
  fadeInFrames = 20,
}) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 등장 페이드인
  const fadeIn = interpolate(rel, [0, fadeInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃 (마지막 15프레임)
  const fadeOut = interpolate(rel, [durationFrames - 15, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const mult = INTENSITY_MULTIPLIER[intensity];
  const finalOpacity = Math.min(1, opacity * mult) * Math.min(fadeIn, fadeOut);

  // primaryColor를 rgba로 변환 (hex → rgb 간이 파싱)
  const hex = primaryColor.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const rgb = `${r},${g},${b}`;

  // 그라디언트 방향: upward = bottom → top (하단에서 위로)
  const gradientDir = direction === "upward" ? "to top" : "to bottom";

  // 배치: upward → 화면 하단 고정 / downward → 화면 상단 고정
  const positionStyle =
    direction === "upward" ? { bottom: 0, top: "auto" } : { top: 0, bottom: "auto" };

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        ...positionStyle,
        width,
        height: gradientHeight,
        transform: `translate(${x}px, ${y}px)`,
        opacity: finalOpacity,
        pointerEvents: "none",
        // 하단에서 위로 퍼지는 부드러운 그라디언트
        background: [
          `linear-gradient(${gradientDir},`,
          `  rgba(${rgb}, 0.92) 0%,`,
          `  rgba(${rgb}, 0.62) 25%,`,
          `  rgba(${rgb}, 0.32) 55%,`,
          `  rgba(${rgb}, 0.08) 80%,`,
          `  rgba(${rgb}, 0.00) 100%`,
          `)`,
        ].join(" "),
      }}
    />
  );
};
