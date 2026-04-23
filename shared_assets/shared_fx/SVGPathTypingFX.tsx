import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * SVGPathTypingFX — 패스를 따라 써지는 듯한 텍스트 효과
 *
 * 글자가 마치 보이지 않는 펜에 의해 그려지듯 나타나는 세련된 효과입니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, strokeWidth
 */

interface SVGPathTypingFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  strokeWidth?: number;
}

export const SVGPathTypingFX: React.FC<SVGPathTypingFXProps> = ({
  startFrame = 0,
  durationFrames = 90,
  x = 0,
  y = 0,
  text,
  fontSize = "100px",
  color = "#FFFFFF",
  strokeWidth = 2,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 전체 애니메이션 진행도 (0 ~ 1)
  const progress = interpolate(rel, [0, durationFrames - 10], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.42, 0, 0.58, 1),
  });

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
      }}
    >
      <svg width="1000" height="300" viewBox="0 0 1000 300" style={{ overflow: "visible" }}>
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <text
          x="500"
          y="150"
          textAnchor="middle"
          dominantBaseline="middle"
          style={{
            fill: "none",
            stroke: color,
            strokeWidth: strokeWidth,
            fontSize,
            fontWeight: "900",
            fontFamily: "sans-serif",
            strokeDasharray: 2000,
            strokeDashoffset: 2000 * (1 - progress),
            filter: "url(#glow)",
          }}
        >
          {text}
        </text>

        {/* 채워지는 효과 (애니메이션 후반부) */}
        <text
          x="500"
          y="150"
          textAnchor="middle"
          dominantBaseline="middle"
          style={{
            fill: color,
            opacity: interpolate(progress, [0.7, 1], [0, 1]),
            fontSize,
            fontWeight: "900",
            fontFamily: "sans-serif",
          }}
        >
          {text}
        </text>
      </svg>
    </div>
  );
};
