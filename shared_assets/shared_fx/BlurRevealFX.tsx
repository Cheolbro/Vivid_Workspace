import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * BlurRevealFX — 안개 속 등장 텍스트
 *
 * 고급스러운 다큐멘터리 느낌으로 텍스트가 안개에서 빠져나오듯 등장합니다.
 * blur 20px→0 + opacity 0→1 + spring 위치 안착 조합.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, revealFrames
 */

interface BlurRevealFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  revealFrames?: number; // 등장 연출 구간 길이 (기본 30프레임 = 1초)
}

export const BlurRevealFX: React.FC<BlurRevealFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  fontSize = "72px",
  color = "#FFFFFF",
  revealFrames = 30,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // blur: 20px → 0px (easeOut)
  const blur = interpolate(rel, [0, revealFrames], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });

  // opacity: 0 → 1 (앞 60% 구간에서 완료)
  const opacity = interpolate(rel, [0, Math.round(revealFrames * 0.65)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });

  // spring: 위에서 스르륵 안착 (damping 높여 부드럽게)
  const settle = spring({
    fps,
    frame: rel,
    config: { damping: 22, stiffness: 75, mass: 0.9 },
    durationInFrames: revealFrames + 10,
  });
  // 0→1 → Y 오프셋 -18px → 0px
  const yOffset = interpolate(settle, [0, 1], [-18, 0]);

  // 퇴장 페이드아웃 (마지막 10프레임)
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, calc(-50% + ${yOffset}px))`,
        opacity: opacity * fadeOut,
        filter: `blur(${blur}px)`,
        fontSize,
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
        fontWeight: "800",
        color,
        whiteSpace: "nowrap",
        letterSpacing: "0.025em",
        lineHeight: 1.2,
        textShadow: "2px 4px 18px rgba(0,0,0,0.9)",
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
};
