import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * VignetteFX — 비네팅 효과
 *
 * 화면 외곽을 어둡게 눌러주어 중앙 콘텐츠에 시선을 집중시킵니다.
 * 다큐멘터리·심층 분석 장면에 어울리는 무게감 있는 분위기 연출.
 * radial-gradient: 중앙 투명 → 외곽 어둠.
 * interpolate로 등장 약 1초(30프레임) 동안 자연스럽게 스며듭니다.
 *
 * commonProps  : startFrame, durationFrames (x, y 미사용)
 * specificProps: intensity, color, fadeInFrames
 */

interface VignetteFXProps {
  startFrame?: number;
  durationFrames?: number;
  intensity?: number; // 외곽 어두운 정도 0.0~1.0 (기본 0.75)
  color?: string; // 비네팅 색상 (기본: 검정)
  fadeInFrames?: number; // 스며드는 구간 (기본 30프레임 = 1초)
}

export const VignetteFX: React.FC<VignetteFXProps> = ({
  startFrame = 0,
  durationFrames = 180,
  intensity = 0.75,
  color = "0, 0, 0", // RGB 값만 (rgba 조합을 위해)
  fadeInFrames = 30,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 등장: fadeInFrames 동안 0 → intensity
  const opacity = interpolate(rel, [0, fadeInFrames], [0, intensity], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃 (마지막 20프레임)
  const fadeOut = interpolate(rel, [durationFrames - 20, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const combinedOpacity = opacity * fadeOut;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        width,
        height,
        opacity: combinedOpacity,
        pointerEvents: "none",
        // 중앙 투명 → 외곽 어두운 radial-gradient
        background: [
          `radial-gradient(ellipse at center,`,
          `  rgba(${color}, 0) 40%,`,
          `  rgba(${color}, 0.6) 70%,`,
          `  rgba(${color}, 0.95) 100%`,
          `)`,
        ].join(" "),
      }}
    />
  );
};
