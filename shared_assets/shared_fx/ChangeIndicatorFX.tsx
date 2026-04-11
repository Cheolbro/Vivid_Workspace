import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { TrendingUp, TrendingDown } from "lucide-react";

/**
 * ChangeIndicatorFX — 상승/하락 지표 표시
 *
 * '코스피 +3.2%' / '금리 -0.5%p' 처럼 증감을 한눈에 보여줍니다.
 * spring 바운스로 팝인 후 숫자가 카운팅되며 화살표 아이콘이 함께 등장.
 * 한국 주식 관례: 상승=빨강, 하락=파랑.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: value, prefix, suffix, fontSize, decimals, label
 */

interface ChangeIndicatorFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  value?: number; // 양수=상승(빨강), 음수=하락(파랑)
  prefix?: string; // 예: "코스피 "
  suffix?: string; // 예: "%", "p"
  fontSize?: string;
  decimals?: number;
  label?: string; // 하단 보조 텍스트
}

const formatter = (v: number, decimals: number) =>
  new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(v));

export const ChangeIndicatorFX: React.FC<ChangeIndicatorFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  value = 3.2,
  prefix = "",
  suffix = "%",
  fontSize = "80px",
  decimals = 1,
  label = "",
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const isPositive = value >= 0;
  const color = isPositive ? "#FF3333" : "#3399FF"; // 상승=빨강, 하락=파랑

  // spring 팝인 (scale 0 → 1, 약간 Overshoot)
  const scale = spring({
    fps,
    frame: rel,
    config: { damping: 14, stiffness: 130, mass: 0.55 },
    durationInFrames: 30,
  });

  // 숫자 카운팅 (0 → |value|)
  const countEnd = Math.round(durationFrames * 0.75);
  const currentValue = interpolate(rel, [0, countEnd], [0, Math.abs(value)], {
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

  const iconSize = parseInt(fontSize, 10) * 0.85 || 68;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity: fadeOut,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "6px",
        pointerEvents: "none",
        whiteSpace: "nowrap",
      }}
    >
      {/* 메인 행: 아이콘 + 숫자 */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        {isPositive ? (
          <TrendingUp size={iconSize} color={color} strokeWidth={2.5} />
        ) : (
          <TrendingDown size={iconSize} color={color} strokeWidth={2.5} />
        )}
        <span
          style={{
            fontSize,
            fontWeight: "900",
            color,
            letterSpacing: "-0.02em",
            lineHeight: 1,
            textShadow: "2px 4px 16px rgba(0,0,0,0.85)",
          }}
        >
          {prefix}
          {isPositive ? "+" : "−"}
          {formatter(currentValue, decimals)}
          {suffix}
        </span>
      </div>

      {/* 보조 레이블 */}
      {label && (
        <span
          style={{
            fontSize: `calc(${fontSize} * 0.4)`,
            fontWeight: "700",
            color: "rgba(255,255,255,0.75)",
            textShadow: "1px 2px 8px rgba(0,0,0,0.8)",
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
};
