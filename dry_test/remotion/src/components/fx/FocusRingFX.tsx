import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * FocusRingFX — 동심원 타겟팅
 *
 * 차트·이미지·텍스트에서 특정 지점을 "바로 여기!" 라고 짚어줍니다.
 * 2~3개의 얇은 원형 테두리가 중심에서 밖으로 퍼져나가며 루핑됩니다.
 * 스나이퍼 조준경 / 레이더 스캔 분위기.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: ringColor, ringCount, maxSize, strokeWidth, cycleDuration
 */

interface FocusRingFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  ringColor?: string; // 링 색상 (기본: 황금)
  ringCount?: number; // 링 개수 2~4 (기본 3)
  maxSize?: number; // 최대 반경 (px, 기본 120)
  strokeWidth?: number; // 테두리 두께 (px, 기본 2)
  cycleDuration?: number; // 한 링의 확산 주기 (프레임, 기본 40)
}

export const FocusRingFX: React.FC<FocusRingFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  x = 0,
  y = 0,
  ringColor = "#FFD700",
  ringCount = 3,
  maxSize = 120,
  strokeWidth = 2,
  cycleDuration = 40,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 전체 페이드인 (10프레임) / 페이드아웃 (12프레임)
  const fadeIn = interpolate(rel, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(rel, [durationFrames - 12, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const globalOpacity = Math.min(fadeIn, fadeOut);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  const rings = Array.from({ length: ringCount }, (_, i) => {
    // 각 링은 cycleDuration / ringCount 만큼 위상(phase) 오프셋을 가짐
    const phaseOffset = (cycleDuration / ringCount) * i;
    const localFrame = (((rel - phaseOffset) % cycleDuration) + cycleDuration) % cycleDuration;

    // 0→1 진행도 (확산)
    const progress = localFrame / cycleDuration;

    // 반경: 중앙 작은 점(8px) → maxSize
    const radius = 8 + progress * (maxSize - 8);

    // 링 자체 opacity: 등장(0→0.3) ~ 진행(0.3→0.85) ~ 소멸(0.85→0) — 끝에서 사라짐
    const ringOpacity = interpolate(progress, [0, 0.08, 0.75, 1.0], [0, 0.9, 0.9, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

    const diameter = radius * 2;

    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: cx - radius,
          top: cy - radius,
          width: diameter,
          height: diameter,
          border: `${strokeWidth}px solid ${ringColor}`,
          borderRadius: "50%",
          opacity: ringOpacity,
          boxShadow: `0 0 ${strokeWidth * 3}px ${ringColor}66`,
          pointerEvents: "none",
        }}
      />
    );
  });

  // 중심점: 작은 십자선 (조준경 느낌)
  const crossSize = 10;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        opacity: globalOpacity,
        pointerEvents: "none",
      }}
    >
      {/* 확산 링들 */}
      {rings}

      {/* 중심 십자선 — 가로 */}
      <div
        style={{
          position: "absolute",
          left: cx - crossSize,
          top: cy - strokeWidth / 2,
          width: crossSize * 2,
          height: strokeWidth,
          background: ringColor,
          opacity: 0.9,
          boxShadow: `0 0 4px ${ringColor}`,
        }}
      />
      {/* 중심 십자선 — 세로 */}
      <div
        style={{
          position: "absolute",
          left: cx - strokeWidth / 2,
          top: cy - crossSize,
          width: strokeWidth,
          height: crossSize * 2,
          background: ringColor,
          opacity: 0.9,
          boxShadow: `0 0 4px ${ringColor}`,
        }}
      />
    </div>
  );
};
