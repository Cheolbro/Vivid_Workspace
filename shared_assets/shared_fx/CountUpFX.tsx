import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * CountUpFX — 정밀 숫자 카운팅
 *
 * '가계부채 1,000조'처럼 거대한 숫자가 굴러가며 압도적인 느낌을 줍니다.
 * react-countup 금지 — useCurrentFrame + interpolate 네이티브 구현.
 * Intl.NumberFormat으로 천 단위 콤마 자동 처리.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: startValue, endValue, prefix, suffix, fontSize, color, countDuration
 */

interface CountUpFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  startValue?: number; // 시작 숫자
  endValue?: number; // 목표 숫자
  prefix?: string; // 앞 단위 (예: ₩, $)
  suffix?: string; // 뒤 단위 (예: 조, 원, %)
  fontSize?: string;
  color?: string;
  countDuration?: number; // 카운팅 구간 (프레임 수, 기본 전체 duration의 80%)
  decimals?: number; // 소수점 자리수
}

const formatter = (value: number, decimals: number) =>
  new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

export const CountUpFX: React.FC<CountUpFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  startValue = 0,
  endValue = 1000,
  prefix = "",
  suffix = "",
  fontSize = "96px",
  color = "#FFD700",
  countDuration,
  decimals = 0,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const countEnd = countDuration ?? Math.round(durationFrames * 0.8);

  // 등장 페이드인 (6프레임)
  const opacity = interpolate(rel, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 숫자 카운팅: easeOut 커브로 초반에 빠르고 끝에서 안착
  const currentValue = interpolate(rel, [0, countEnd], [startValue, endValue], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const displayValue = formatter(currentValue, decimals);

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity,
        display: "flex",
        alignItems: "baseline",
        gap: "4px",
        pointerEvents: "none",
        whiteSpace: "nowrap",
      }}
    >
      {/* prefix */}
      {prefix && (
        <span
          style={{
            fontSize: `calc(${fontSize} * 0.6)`,
            fontWeight: "800",
            color,
            letterSpacing: "0",
            textShadow: "2px 3px 12px rgba(0,0,0,0.8)",
          }}
        >
          {prefix}
        </span>
      )}

      {/* 숫자 본체 */}
      <span
        style={{
          fontSize,
          fontWeight: "900",
          color,
          letterSpacing: "-0.02em",
          lineHeight: 1,
          textShadow: "2px 4px 20px rgba(0,0,0,0.85), 0 0 40px rgba(255,215,0,0.2)",
        }}
      >
        {displayValue}
      </span>

      {/* suffix */}
      {suffix && (
        <span
          style={{
            fontSize: `calc(${fontSize} * 0.55)`,
            fontWeight: "800",
            color,
            letterSpacing: "0",
            textShadow: "2px 3px 12px rgba(0,0,0,0.8)",
            alignSelf: "flex-end",
            paddingBottom: "4px",
          }}
        >
          {suffix}
        </span>
      )}
    </div>
  );
};
