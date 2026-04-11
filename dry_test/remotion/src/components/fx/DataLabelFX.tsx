import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

/**
 * DataLabelFX — 데이터 콜아웃 레이블
 *
 * 차트나 이미지 위 특정 포인트에 반투명 말풍선으로 수치를 표시합니다.
 * spring 스케일 팝인으로 등장하며, 꼬리(tail)가 포인트를 가리킵니다.
 * 꼬리 방향: "down"(기본, 포인트 위 레이블), "up"(포인트 아래 레이블)
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, subText, tailDirection, bgColor, textColor, fontSize
 */

interface DataLabelFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string; // 메인 수치 (예: "1,862조")
  subText?: string; // 보조 설명 (예: "가계부채")
  tailDirection?: "up" | "down"; // 꼬리 방향 (레이블 기준 아래=down, 위=up)
  bgColor?: string; // 배경 색상
  textColor?: string; // 메인 텍스트 색상
  fontSize?: string;
  paddingH?: number; // 좌우 패딩 (px)
  paddingV?: number; // 상하 패딩 (px)
}

const TAIL_SIZE = 14; // 꼬리 삼각형 크기

export const DataLabelFX: React.FC<DataLabelFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  subText = "",
  tailDirection = "down",
  bgColor = "rgba(10, 10, 20, 0.82)",
  textColor = "#FFD700",
  fontSize = "52px",
  paddingH = 28,
  paddingV = 16,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // spring 팝인: 스케일 0 → 1 (약간 Overshoot)
  const scale = spring({
    fps,
    frame: rel,
    config: { damping: 13, stiffness: 140, mass: 0.5 },
    durationInFrames: 28,
  });

  // 등장 페이드인
  const fadeIn = interpolate(rel, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 퇴장 페이드아웃
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // 꼬리(tail) SVG: 레이블 하단(down) 또는 상단(up)
  const tailDown = (
    <svg
      width={TAIL_SIZE * 2}
      height={TAIL_SIZE}
      viewBox={`0 0 ${TAIL_SIZE * 2} ${TAIL_SIZE}`}
      style={{ display: "block", margin: "0 auto" }}
    >
      <polygon points={`0,0 ${TAIL_SIZE * 2},0 ${TAIL_SIZE},${TAIL_SIZE}`} fill={bgColor} />
    </svg>
  );

  const tailUp = (
    <svg
      width={TAIL_SIZE * 2}
      height={TAIL_SIZE}
      viewBox={`0 0 ${TAIL_SIZE * 2} ${TAIL_SIZE}`}
      style={{ display: "block", margin: "0 auto" }}
    >
      <polygon
        points={`${TAIL_SIZE},0 0,${TAIL_SIZE} ${TAIL_SIZE * 2},${TAIL_SIZE}`}
        fill={bgColor}
      />
    </svg>
  );

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${scale})`,
        transformOrigin: tailDirection === "down" ? "50% 100%" : "50% 0%",
        opacity: Math.min(fadeIn, fadeOut),
        pointerEvents: "none",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
      }}
    >
      {/* 꼬리 위 (up) */}
      {tailDirection === "up" && tailUp}

      {/* 레이블 박스 */}
      <div
        style={{
          background: bgColor,
          borderRadius: "12px",
          padding: `${paddingV}px ${paddingH}px`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "4px",
          boxShadow: "0 4px 24px rgba(0,0,0,0.55), 0 0 0 1.5px rgba(255,255,255,0.12)",
          whiteSpace: "nowrap",
        }}
      >
        {/* 메인 수치 */}
        <span
          style={{
            fontSize,
            fontWeight: "900",
            color: textColor,
            letterSpacing: "-0.02em",
            lineHeight: 1.1,
            textShadow: "1px 2px 10px rgba(0,0,0,0.7)",
          }}
        >
          {text}
        </span>

        {/* 보조 텍스트 */}
        {subText && (
          <span
            style={{
              fontSize: `calc(${fontSize} * 0.45)`,
              fontWeight: "700",
              color: "rgba(255,255,255,0.75)",
              textShadow: "1px 1px 6px rgba(0,0,0,0.6)",
            }}
          >
            {subText}
          </span>
        )}
      </div>

      {/* 꼬리 아래 (down) */}
      {tailDirection === "down" && tailDown}
    </div>
  );
};
