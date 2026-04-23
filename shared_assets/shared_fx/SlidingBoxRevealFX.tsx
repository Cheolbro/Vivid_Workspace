import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * SlidingBoxRevealFX — 박스가 스쳐 지나가며 텍스트를 드러내는 효과
 *
 * 스타일리시한 편집 감각을 주는 효과로, 뉴스나 매거진 스타일 연출에 적합합니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, boxColor
 */

interface SlidingBoxRevealFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  boxColor?: string;
}

export const SlidingBoxRevealFX: React.FC<SlidingBoxRevealFXProps> = ({
  startFrame = 0,
  durationFrames = 60,
  x = 0,
  y = 0,
  text,
  fontSize = "80px",
  color = "#FFFFFF",
  boxColor = "#007AFF",
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 스프링 애니메이션으로 박스 이동 제어
  const spr = spring({
    frame: rel,
    fps,
    config: { damping: 15, stiffness: 100 },
  });

  // 박스 위치: 좌측 끝(-100%)에서 우측 끝(100%)으로 이동
  const boxTranslate = interpolate(spr, [0, 0.5, 1], [-105, 0, 105]);

  // 텍스트 페이드/스케일 (박스가 중앙을 지날 때 나타남)
  const textOpacity = interpolate(spr, [0.3, 0.5], [0, 1]);
  const textScale = interpolate(spr, [0.3, 0.5], [0.95, 1], {
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
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        padding: "20px 40px",
      }}
    >
      {/* 텍스트 레이어 */}
      <div
        style={{
          fontSize,
          fontWeight: "900",
          color,
          opacity: textOpacity,
          transform: `scale(${textScale})`,
          zIndex: 1,
          fontFamily: "sans-serif",
          textShadow: "0 4px 10px rgba(0,0,0,0.3)",
        }}
      >
        {text}
      </div>

      {/* 슬라이딩 박스 레이어 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          backgroundColor: boxColor,
          transform: `translateX(${boxTranslate}%)`,
          zIndex: 2,
          boxShadow: "0 0 30px rgba(0,0,0,0.2)",
        }}
      />
    </div>
  );
};
