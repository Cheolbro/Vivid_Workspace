import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * SimpleBarChartFX — 간단한 막대 차트
 *
 * 경제 비교 데이터를 시각화합니다 (예: 국가별 부채비율 비교).
 * spring으로 막대가 아래에서 위로 자라납니다.
 * 막대 위에 값 레이블이 spring 딜레이로 팝인.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: bars, maxValue, barWidth, barGap, showValues, fontSize
 */

interface BarItem {
  label: string;
  value: number;
  color?: string;
}

interface SimpleBarChartFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  bars?: BarItem[];
  maxValue?: number; // Y축 최대값 (미지정 시 최대 bar 값의 110%)
  chartHeight?: number; // 차트 최대 높이 (px)
  barWidth?: number; // 막대 너비 (px)
  barGap?: number; // 막대 간격 (px)
  showValues?: boolean; // 값 레이블 표시 여부
  fontSize?: string;
  decimals?: number;
}

const DEFAULT_BARS: BarItem[] = [
  { label: "한국", value: 50, color: "#FF3333" },
  { label: "미국", value: 130, color: "#3399FF" },
  { label: "일본", value: 260, color: "#FFD700" },
];

export const SimpleBarChartFX: React.FC<SimpleBarChartFXProps> = ({
  startFrame = 0,
  durationFrames = 150,
  x = 0,
  y = 0,
  bars = DEFAULT_BARS,
  maxValue,
  chartHeight = 320,
  barWidth = 100,
  barGap = 28,
  showValues = true,
  fontSize = "36px",
  decimals = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  const computedMax = maxValue ?? Math.max(...bars.map((b) => b.value)) * 1.12;

  // 퇴장 페이드아웃
  const fadeOut = interpolate(rel, [durationFrames - 10, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  const totalWidth = bars.length * barWidth + (bars.length - 1) * barGap;
  const fmt = (v: number) =>
    new Intl.NumberFormat("ko-KR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(v);

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
        alignItems: "center",
      }}
    >
      {/* 막대 영역 */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: `${barGap}px`,
          height: `${chartHeight}px`,
          borderBottom: "3px solid rgba(255,255,255,0.4)",
          paddingBottom: "0",
        }}
      >
        {bars.map((bar, i) => {
          // 각 막대마다 시작 딜레이 (stagger)
          const delay = i * 5;
          const barProgress = spring({
            fps,
            frame: Math.max(0, rel - delay),
            config: { damping: 18, stiffness: 90, mass: 0.7 },
            durationInFrames: 40,
          });

          const targetHeight = (bar.value / computedMax) * chartHeight;
          const currentHeight = barProgress * targetHeight;

          // 값 레이블: 막대가 70% 자란 후 팝인
          const labelDelay = delay + 20;
          const labelScale = spring({
            fps,
            frame: Math.max(0, rel - labelDelay),
            config: { damping: 12, stiffness: 150, mass: 0.4 },
            durationInFrames: 20,
          });

          const barColor = bar.color ?? "#FFD700";

          return (
            <div
              key={i}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "flex-end",
                height: "100%",
                gap: "8px",
              }}
            >
              {/* 값 레이블 */}
              {showValues && (
                <span
                  style={{
                    fontSize,
                    fontWeight: "900",
                    color: barColor,
                    transform: `scale(${labelScale})`,
                    whiteSpace: "nowrap",
                    textShadow: "1px 2px 10px rgba(0,0,0,0.85)",
                    minHeight: "1em",
                    display: "block",
                  }}
                >
                  {fmt(bar.value)}
                </span>
              )}

              {/* 막대 본체 */}
              <div
                style={{
                  width: `${barWidth}px`,
                  height: `${currentHeight}px`,
                  background: `linear-gradient(to top, ${barColor}CC, ${barColor})`,
                  borderRadius: "6px 6px 0 0",
                  boxShadow: `0 0 18px ${barColor}66`,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* X축 레이블 */}
      <div
        style={{
          display: "flex",
          gap: `${barGap}px`,
          marginTop: "12px",
        }}
      >
        {bars.map((bar, i) => (
          <span
            key={i}
            style={{
              width: `${barWidth}px`,
              textAlign: "center",
              fontSize: `calc(${fontSize} * 0.85)`,
              fontWeight: "700",
              color: "rgba(255,255,255,0.85)",
              textShadow: "1px 2px 8px rgba(0,0,0,0.8)",
              whiteSpace: "nowrap",
            }}
          >
            {bar.label}
          </span>
        ))}
      </div>
    </div>
  );
};
