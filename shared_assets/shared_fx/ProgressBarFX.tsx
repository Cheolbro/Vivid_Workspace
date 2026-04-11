import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * ProgressBarFX — 진행률 바
 *
 * '목표달성률 78%' 같은 단일 지표를 씩씩하게 채워나가는 연출.
 * 화면 하단(또는 지정 위치)에 얇은 바가 왼쪽부터 오른쪽으로 채워집니다.
 * 끝 값 도달 후 짧게 pulse로 완료를 알립니다.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: targetPercent, barColor, trackColor, barHeight, barWidth,
 *               label, showPercent, fontSize
 */

interface ProgressBarFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  targetPercent?: number; // 0~100
  barColor?: string;
  trackColor?: string; // 배경 트랙 색상
  barHeight?: number; // 바 두께 (px)
  barWidth?: number; // 바 전체 너비 (px)
  label?: string; // 상단 레이블 (예: "목표 달성률")
  showPercent?: boolean; // 퍼센트 수치 우측 표시
  fontSize?: string;
}

export const ProgressBarFX: React.FC<ProgressBarFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  targetPercent = 78,
  barColor = "#FFD700",
  trackColor = "rgba(255,255,255,0.18)",
  barHeight = 14,
  barWidth = 700,
  label = "",
  showPercent = true,
  fontSize = "52px",
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // 채움 구간: 전체 duration의 75%
  const fillEnd = Math.round(durationFrames * 0.75);
  const fillProgress = interpolate(rel, [0, fillEnd], [0, targetPercent / 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  // 수치 (0% → targetPercent%)
  const currentPercent = fillProgress * 100;

  // 완료 pulse: fillEnd 이후 살짝 glow 강화
  const glowPulse = interpolate(rel, [fillEnd, fillEnd + 8, fillEnd + 18], [1, 1.8, 1], {
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

  const filledWidth = barWidth * fillProgress;
  const glowStr = `0 0 ${12 * glowPulse}px ${barColor}, 0 0 ${6 * glowPulse}px ${barColor}`;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity: fadeOut,
        pointerEvents: "none",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
        alignItems: "flex-start",
      }}
    >
      {/* 상단: 레이블 + 퍼센트 수치 */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          width: `${barWidth}px`,
          alignItems: "baseline",
        }}
      >
        {label && (
          <span
            style={{
              fontSize: `calc(${fontSize} * 0.55)`,
              fontWeight: "700",
              color: "rgba(255,255,255,0.85)",
              textShadow: "1px 2px 8px rgba(0,0,0,0.8)",
              whiteSpace: "nowrap",
            }}
          >
            {label}
          </span>
        )}
        {showPercent && (
          <span
            style={{
              fontSize,
              fontWeight: "900",
              color: barColor,
              letterSpacing: "-0.02em",
              lineHeight: 1,
              textShadow: `2px 4px 16px rgba(0,0,0,0.85), ${glowStr}`,
              marginLeft: "auto",
            }}
          >
            {Math.round(currentPercent)}%
          </span>
        )}
      </div>

      {/* 트랙 */}
      <div
        style={{
          width: `${barWidth}px`,
          height: `${barHeight}px`,
          background: trackColor,
          borderRadius: `${barHeight}px`,
          overflow: "hidden",
          boxShadow: "inset 0 1px 4px rgba(0,0,0,0.4)",
        }}
      >
        {/* 채움 바 */}
        <div
          style={{
            width: `${filledWidth}px`,
            height: "100%",
            background: `linear-gradient(to right, ${barColor}BB, ${barColor})`,
            borderRadius: `${barHeight}px`,
            boxShadow: glowStr,
            transition: "none",
          }}
        />
      </div>
    </div>
  );
};
