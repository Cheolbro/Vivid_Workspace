import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * ScreenFlashFX — 화면 플래시 전환
 *
 * "증발?!", "충격" 키워드에 카메라 플래시가 터지듯 시각적 충격을 줍니다.
 * opacity 1 → 0 으로 날카롭게 떨어지는 단발성 이펙트.
 * 여러 번 반복하려면 startFrame이 다른 인스턴스를 여러 개 배치하세요.
 *
 * commonProps  : startFrame, durationFrames (x, y 미사용)
 * specificProps: flashColor, flashDuration, peakHold
 */

interface ScreenFlashFXProps {
  startFrame?: number;
  durationFrames?: number;
  flashColor?: string; // 플래시 색상 (기본: 흰색)
  flashDuration?: number; // 플래시 소멸 구간 (프레임, 기본 12)
  peakHold?: number; // 최대 밝기 유지 구간 (프레임, 기본 2)
}

export const ScreenFlashFX: React.FC<ScreenFlashFXProps> = ({
  startFrame = 0,
  durationFrames = 20,
  flashColor = "rgba(255, 255, 255, 1)",
  flashDuration = 12,
  peakHold = 2,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // peakHold 구간: 최대 불투명도 유지 → 이후 flashDuration 동안 날카롭게 소멸
  const opacity = interpolate(rel, [0, peakHold, peakHold + flashDuration], [1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.exp), // 급격한 하강: 플래시 특유의 날카로움
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        background: flashColor,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};
