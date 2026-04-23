import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * MetallicReflectionFX — 금속 재질 반사광 효과
 *
 * 원유 저장 탱크 등 금속 표면에 번쩍이는 반사광(Sheen/Glare)이
 * 지정된 각도로 스윽 지나가는 애니메이션을 연출하여 금속 재질감을 강조합니다.
 *
 * commonProps  : startFrame, durationFrames
 * specificProps: angle, thickness, highlightColor, opacity, cycleFrames, blurPx
 */

interface MetallicReflectionFXProps {
  startFrame?: number;
  durationFrames?: number;
  angle?: number;
  thickness?: number;
  highlightColor?: string;
  opacity?: number;
  cycleFrames?: number;
  blurPx?: number;
}

export const MetallicReflectionFX: React.FC<MetallicReflectionFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  angle = 35,
  thickness = 150,
  highlightColor = "rgba(255, 255, 255, 0.65)",
  opacity = 0.85,
  cycleFrames = 90,
  blurPx = 12,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 주기적으로 빛이 지나가도록 진행도 계산
  const progress = (rel % cycleFrames) / cycleFrames;

  // easing을 주어 가운데서 빠르게 지나가도록 연출
  const easedProgress = Easing.inOut(Easing.ease)(progress);

  // 화면 대각선 길이 계산 (넉넉하게 커버하기 위함)
  const diagonal = Math.sqrt(width * width + height * height) * 1.5;

  // 이동 범위: 화면 밖에서 밖으로
  const translateX = interpolate(easedProgress, [0, 1], [-diagonal / 2, diagonal / 2]);

  // 퇴장 시 페이드아웃 (마지막 10프레임)
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        overflow: "hidden",
        opacity: opacity * fadeOut,
        zIndex: 5,
      }}
    >
      {/* 1차 반사광 (넓고 은은한 빛) */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          width: diagonal,
          height: thickness,
          background: `linear-gradient(90deg, rgba(255,255,255,0) 0%, ${highlightColor} 50%, rgba(255,255,255,0) 100%)`,
          transform: `translate(-50%, -50%) rotate(${angle}deg) translateX(${translateX}px)`,
          filter: blurPx > 0 ? `blur(${blurPx}px)` : "none",
          mixBlendMode: "overlay", // 금속 표면에 어울리는 블렌드 모드
        }}
      />
      {/* 2차 반사광 (좁고 강렬한 코어 빛) */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          width: diagonal,
          height: thickness * 0.25,
          background: `linear-gradient(90deg, rgba(255,255,255,0) 0%, #FFFFFF 50%, rgba(255,255,255,0) 100%)`,
          transform: `translate(-50%, -50%) rotate(${angle}deg) translateX(${translateX * 1.05}px)`,
          filter: blurPx > 0 ? `blur(${blurPx * 0.5}px)` : "none",
          mixBlendMode: "screen", // 강한 하이라이트
        }}
      />
    </div>
  );
};
