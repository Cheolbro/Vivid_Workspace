import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * VerticalMaskSlideFX — 마스크 아래에서 위로 슥 올라오는 텍스트 효과
 *
 * 깔끔하고 정돈된 느낌을 주며, 목록 나열이나 핵심 포인트 제시에 좋습니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, maskHeight
 */

interface VerticalMaskSlideFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  maskHeight?: number;
}

export const VerticalMaskSlideFX: React.FC<VerticalMaskSlideFXProps> = ({
  startFrame = 0,
  durationFrames = 60,
  x = 0,
  y = 0,
  text,
  fontSize = "85px",
  color = "#FFFFFF",
  maskHeight = 120,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 스프링으로 부드러운 상승 효과
  const spr = spring({
    frame: rel,
    fps,
    config: { damping: 15, stiffness: 100 },
  });

  const translateY = interpolate(spr, [0, 1], [maskHeight, 0]);
  const opacity = interpolate(rel, [0, 10], [0, 1]);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        overflow: "hidden", // 마스크 역할
        height: maskHeight,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          fontSize,
          fontWeight: "900",
          color,
          opacity,
          transform: `translateY(${translateY}px)`,
          fontFamily: "sans-serif",
          textAlign: "center",
          whiteSpace: "nowrap",
        }}
      >
        {text}
      </div>
    </div>
  );
};
