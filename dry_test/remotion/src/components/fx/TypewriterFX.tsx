import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

/**
 * TypewriterFX — 타이핑 효과
 *
 * 실시간으로 경제 리포트가 작성되는 듯한 신뢰감을 연출합니다.
 * 커서는 0.5초(15프레임) 간격으로 깜빡이며, 타이핑 완료 후 3회 깜빡이고 소멸.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, fontSize, color, speed
 */

interface TypewriterFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  fontSize?: string;
  color?: string;
  speed?: number; // 초당 글자 수 (chars per second)
}

export const TypewriterFX: React.FC<TypewriterFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  fontSize = "64px",
  color = "#FFFFFF",
  speed = 7,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // text prop 누락 방어 (props 생성 오류 시 크래시 방지)
  if (!text) return null;

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 노출할 글자 수 (프레임에 비례)
  const charsPerFrame = speed / fps;
  const charsToShow = Math.min(text.length, Math.floor(rel * charsPerFrame));
  const displayText = text.substring(0, charsToShow);

  // 전체 페이드인 (첫 4프레임)
  const containerOpacity = interpolate(rel, [0, 4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 커서 깜빡임: 0.5초(15프레임) 주기
  const blinkPeriod = Math.round(fps * 0.5);

  // 타이핑 완료 시점 (rel 기준)
  const typingDoneRel = Math.ceil(text.length / charsPerFrame);
  const afterTypingRel = rel - typingDoneRel;
  const totalBlinkFrames = blinkPeriod * 2 * 3; // 3회 깜빡임 = on/off × 3

  let showCursor: boolean;
  if (charsToShow < text.length) {
    // 타이핑 중: 커서 항상 표시
    showCursor = true;
  } else if (afterTypingRel >= totalBlinkFrames) {
    // 3회 깜빡임 완료 → 커서 소멸
    showCursor = false;
  } else {
    // 완료 후 3회 깜빡임 (afterTypingRel 기준 — 완료 시점부터 visible 시작)
    showCursor = Math.floor(afterTypingRel / blinkPeriod) % 2 === 0;
  }

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity: containerOpacity,
        fontSize,
        fontWeight: "800",
        color,
        whiteSpace: "nowrap",
        letterSpacing: "0.02em",
        lineHeight: 1.2,
        textShadow: "2px 3px 14px rgba(0,0,0,0.85)",
        pointerEvents: "none",
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
      }}
    >
      {displayText}
      <span
        style={{
          opacity: showCursor ? 1 : 0,
          marginLeft: "3px",
          fontWeight: "300",
          color,
        }}
      >
        |
      </span>
    </div>
  );
};
