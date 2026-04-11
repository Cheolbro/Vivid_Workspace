import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";

/**
 * UnderlineFX — 지능형 밑줄 효과 (All-in-One 시퀀스)
 *
 * [Step 1 · 0~15프레임] 텍스트 등장
 *   revealStyle='fade' : opacity 0 → 1
 *   revealStyle='blur' : opacity 0 → 1  +  blur 10px → 0px
 *
 * [Step 2 · 15프레임 이후] 밑줄 발동
 *   일직선 테이퍼 획: 전반부는 굵고, 중간 이후부터 끝으로 갈수록 점점 얇아짐.
 *   clipPath 기반 왼쪽→오른쪽 드로잉 애니메이션.
 *   텍스트 등장 구간(0~EFFECT_DELAY)에서는 완전히 숨김.
 *
 * commonProps  : startFrame, durationFrames, x, y
 * specificProps: text, revealStyle, fontSize, color, underlineColor, thickness
 */

interface UnderlineFXProps {
  startFrame?: number;
  durationFrames?: number;
  x?: number;
  y?: number;
  text: string;
  revealStyle?: "fade" | "blur";
  fontSize?: string;
  color?: string;
  underlineColor?: string;
  thickness?: number; // 기본 14 (두꺼운 펜 획)
}

const REVEAL_FRAMES = 15;
const EFFECT_DELAY = 15;

export const UnderlineFX: React.FC<UnderlineFXProps> = ({
  startFrame = 0,
  durationFrames = 120,
  x = 0,
  y = 0,
  text,
  revealStyle = "fade",
  fontSize = "72px",
  color = "#FFFFFF",
  underlineColor = "#FF3333",
  thickness = 14,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // text prop 누락 방어
  if (!text) return null;

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // ── Step 1: 텍스트 등장 ─────────────────────────────────────────
  const textOpacity = interpolate(rel, [0, REVEAL_FRAMES], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });

  const blurPx =
    revealStyle === "blur"
      ? interpolate(rel, [0, REVEAL_FRAMES], [10, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.quad),
        })
      : 0;

  // ── Step 2: 밑줄 발동 ───────────────────────────────────────────
  const lineProgress = spring({
    fps,
    frame: Math.max(0, rel - EFFECT_DELAY),
    config: { damping: 24, stiffness: 220, mass: 0.35 },
    durationInFrames: 20,
  });

  // EFFECT_DELAY 이전 구간은 밑줄 완전 숨김 (초기 플래시 방지)
  const revealWidth = rel < EFFECT_DELAY ? 0 : Math.min(lineProgress, 1);

  // ── 퇴장 (마지막 10프레임) ──────────────────────────────────────
  // guard: durationFrames ≤ 10 이면 시작값이 음수가 되어 처음부터 반투명해지는 버그 방지
  const fadeOut = interpolate(
    rel,
    [Math.max(0, durationFrames - 10), Math.max(1, durationFrames)],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const cx = width / 2 + x;
  const cy = height / 2 + y;

  // clipPath 고유 ID (텍스트 기반)
  const clipId = `ul_${text.slice(0, 8).replace(/[^\w]/g, "x")}_${text.length}`;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform: "translate(-50%, -50%)",
        opacity: fadeOut,
        pointerEvents: "none",
      }}
    >
      <div style={{ position: "relative", display: "inline-block" }}>
        {/* 텍스트 본체 */}
        <span
          style={{
            display: "block",
            fontSize,
            fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
            fontWeight: "900",
            color,
            opacity: textOpacity,
            filter: blurPx > 0 ? `blur(${blurPx}px)` : undefined,
            whiteSpace: "nowrap",
            letterSpacing: "0.025em",
            lineHeight: 1.2,
            textShadow: "2px 3px 14px rgba(0,0,0,0.85)",
          }}
        >
          {text}
        </span>

        {/*
          SVG 밑줄 — 일직선 테이퍼 획
          · viewBox "0 0 1 1" + preserveAspectRatio="none" 로 텍스트 너비에 자동 맞춤
          · polygon: 전반 절반(x=0~0.5)은 굵게 유지, 후반 절반(x=0.5~1)은 끝으로 갈수록 얇아짐
          · clipPath: revealWidth(0→1)로 왼쪽부터 오른쪽으로 드로잉
        */}
        <svg
          style={{
            position: "absolute",
            bottom: -(thickness * 2.5),
            left: 0,
            width: "100%",
            height: thickness * 4,
            overflow: "visible",
          }}
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
        >
          <defs>
            <clipPath id={clipId}>
              {/* userSpaceOnUse: viewBox 좌표계(0~1) 기준으로 왼쪽부터 열림 */}
              <rect x={0} y={-0.5} width={revealWidth} height={2} />
            </clipPath>
          </defs>

          {/*
            테이퍼 폴리곤 (6개 꼭짓점):
              좌측 두께: 0.40  |  우측 두께: 0.20

            [블리드 레이어] 잉크 번짐: 메인보다 약간 크고 반투명
              points: 메인 폴리곤을 상하로 ~0.12씩 확장
            [메인 레이어] 선명한 주 획
          */}

          {/* 블리드: 잉크 번짐 (낮은 opacity, 약간 더 큰 형태) */}
          <polygon
            points="0,0.18 0.5,0.18 1,0.31 1,0.69 0.5,0.82 0,0.82"
            fill={underlineColor}
            opacity={0.28}
            clipPath={`url(#${clipId})`}
          />

          {/* 메인 획: 40% → 20% 테이퍼 */}
          <polygon
            points="0,0.30 0.5,0.30 1,0.40 1,0.60 0.5,0.70 0,0.70"
            fill={underlineColor}
            clipPath={`url(#${clipId})`}
          />
        </svg>
      </div>
    </div>
  );
};
