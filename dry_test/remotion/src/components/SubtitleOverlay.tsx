import React from "react";
import { useCurrentFrame } from "remotion";

/**
 * SubtitleOverlay — 슬라이드 Composition 미리보기 전용 자막 레이어
 *
 * previewMode=true 일 때만 렌더링되어, Studio에서 자막 타이밍을 확인할 수 있다.
 * 투명 렌더링(previewMode=false) 시에는 부모 컴포넌트에서 이 컴포넌트를 조건부 제외한다.
 */

export interface SubtitleEntry {
  startFrame: number; // 슬라이드 Composition 내 로컬 프레임
  endFrame: number;
  text: string;
}

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
}

export const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({ subtitles }) => {
  const frame = useCurrentFrame();
  const active = subtitles.find((s) => frame >= s.startFrame && frame < s.endFrame);

  if (!active?.text) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 72,
        left: "8%",
        width: "84%",
        textAlign: "center",
        fontSize: "46px",
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
        fontWeight: "bold",
        color: "#FFFFFF",
        letterSpacing: "0.02em",
        lineHeight: 1.3,
        textShadow: "1px 2px 8px rgba(0,0,0,0.95)",
        background: "rgba(0,0,0,0.38)",
        borderRadius: "10px",
        padding: "10px 24px",
        pointerEvents: "none",
      }}
    >
      {active.text}
    </div>
  );
};
