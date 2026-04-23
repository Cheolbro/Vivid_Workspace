import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * RetroTerminalFX — 고전적인 터미널 타이핑 효과
 *
 * 녹색 폰트와 블록 커서를 사용하여 해킹이나 기록 보관소 느낌을 연출합니다.
 *
 * commonProps: startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, typingSpeed
 */

interface RetroTerminalFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  typingSpeed?: number;
}

export const RetroTerminalFX: React.FC<RetroTerminalFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  fontSize = "50px",
  color = "#00FF41", // Matrix Green
  typingSpeed = 15, // chars per second
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 타이핑 로직
  const charsToShow = Math.min(text.length, Math.floor(rel * (typingSpeed / fps)));
  const displayText = text.substring(0, charsToShow);

  // 커서 깜빡임 (초당 2회)
  const isCursorVisible = Math.floor(rel / (fps / 4)) % 2 === 0;

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        backgroundColor: "rgba(0,0,0,0.8)",
        padding: "20px 30px",
        borderRadius: "5px",
        border: `1px solid ${color}44`,
        boxShadow: `0 0 20px ${color}22`,
        pointerEvents: "none",
        fontFamily: "'Courier New', Courier, monospace", // 터미널 폰트
      }}
    >
      <div style={{ fontSize, color, fontWeight: "bold", textShadow: `0 0 5px ${color}` }}>
        <span style={{ marginRight: "10px" }}>{">"}</span>
        {displayText}
        <span
          style={{
            display: "inline-block",
            width: "20px",
            height: "30px",
            backgroundColor: color,
            marginLeft: "5px",
            verticalAlign: "middle",
            opacity: isCursorVisible ? 1 : 0,
          }}
        />
      </div>
    </div>
  );
};
