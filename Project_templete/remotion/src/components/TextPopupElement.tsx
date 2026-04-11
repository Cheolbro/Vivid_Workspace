import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * TextPopupElement — 텍스트 기반 팝업 오버레이
 *
 * remotion_plan.json에서 type:"Popup" + text 필드를 가진 항목에 사용.
 * 화면 중앙 기준으로 x/y 픽셀 오프셋을 적용하여 위치를 지정한다.
 */

interface TextPopupElementProps {
  text: string; // 표시할 텍스트
  startFrame: number; // 노출 시작 프레임
  durationFrames: number; // 노출 지속 프레임 수
  x?: number; // 중앙 기준 X 오프셋 (px, 양수=오른쪽)
  y?: number; // 중앙 기준 Y 오프셋 (px, 양수=아래쪽)
  fontSize?: string; // CSS font-size (기본: "80px")
  color?: string; // 텍스트 색상 (기본: 흰색)
  fontWeight?: string | number;
}

export const TextPopupElement: React.FC<TextPopupElementProps> = ({
  text,
  startFrame,
  durationFrames,
  x = 0,
  y = 0,
  fontSize = "80px",
  color = "#FFFFFF",
  fontWeight = "bold",
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const fadeIn = Math.min(10, Math.floor(durationFrames * 0.12));
  const fadeOut = durationFrames - fadeIn;

  const opacity = interpolate(rel, [0, fadeIn, fadeOut, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.ease,
  });

  const scale = interpolate(rel, [0, fadeIn], [0.82, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.2)),
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        fontSize,
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
        color,
        fontWeight: String(fontWeight),
        textAlign: "center",
        whiteSpace: "nowrap", // 줄바꿈 방지 (overflow: visible로 viewport 밖까지 허용)
        overflow: "visible",
        lineHeight: 1.25,
        letterSpacing: "0.02em",
        textShadow: "2px 4px 16px rgba(0,0,0,0.85), 0 0 48px rgba(255,255,255,0.15)",
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
};
