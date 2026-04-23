import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * TextPopupElement — Schema v2.0 지원 텍스트 팝업 오버레이
 *
 * textStyle과 animation 속성을 지원하여 다양한 등장 효과와 스타일을 렌더링합니다.
 */

interface TextStyleProps {
  color?: string;
  fontWeight?: string | number;
  shadow?: string;
  background?: string;
  backgroundPadding?: string;
  borderRadius?: string;
  borderLeft?: string;
}

interface AnimationProps {
  in?: string; // slideFromLeft | slideFromRight | slideFromBottom | slideFromTop | fadeIn | scaleUp | typewriter | revealMask
  inDurationFrames?: number;
  out?: string; // fadeOut | scaleDown | none
  outDurationFrames?: number;
  easing?: string; // easeOutBack | easeOutExpo | easeInOutSine | linear
}

interface TextPopupElementProps {
  text: string;
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: string;
  width?: string | number;
  textStyle?: TextStyleProps;
  animation?: AnimationProps;
}

export const TextPopupElement: React.FC<TextPopupElementProps> = ({
  text,
  startFrame,
  durationFrames,
  x = 0,
  y = 0,
  fontSize = "80px",
  width = "90%",
  textStyle = {},
  animation = {},
}) => {
  const frame = useCurrentFrame();
  const { width: videoW, height: videoH } = useVideoConfig();

  const rel = frame - startFrame;
  if (rel < 0 || rel >= durationFrames) return null;

  // Default Animation Configuration
  const animIn = animation.in || "scaleUp";
  const inDur = animation.inDurationFrames || Math.min(10, Math.floor(durationFrames * 0.12));
  const animOut = animation.out || "fadeOut";
  const outDur = animation.outDurationFrames || Math.min(10, Math.floor(durationFrames * 0.12));
  const easingType = animation.easing || "easeOutBack";

  const getEasing = (type: string) => {
    switch (type) {
      case "easeOutExpo":
        return Easing.out(Easing.exp);
      case "easeInOutSine":
        return Easing.inOut(Easing.sin);
      case "linear":
        return Easing.linear;
      case "easeOutBack":
      default:
        return Easing.out(Easing.back(1.2));
    }
  };
  const inEasingFn = getEasing(easingType);

  const outStart = durationFrames - outDur;

  // 1. Opacity Animation
  let opacity = 1;
  const inOpacity = interpolate(rel, [0, inDur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.ease,
  });
  const outOpacity = interpolate(rel, [outStart, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.ease,
  });

  if (animIn === "fadeIn" || animIn === "scaleUp" || animIn.startsWith("slide")) {
    opacity = rel < outStart ? inOpacity : outOpacity;
  } else if (animIn === "typewriter" || animIn === "revealMask") {
    // 등장 중에는 opacity 1, out 구간에서만 fade
    opacity = rel < outStart ? 1 : outOpacity;
  }
  if (animOut === "none" && rel >= outStart) opacity = 1;

  // 2. Transform Animation
  let transform = `translate(-50%, -50%)`;

  // Base scaling from animIn
  let currentScale = 1;
  if (animIn === "scaleUp") {
    currentScale = interpolate(rel, [0, inDur], [0.82, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
  }

  if (animOut === "scaleDown" && rel >= outStart) {
    currentScale = interpolate(rel, [outStart, durationFrames], [1, 0.85], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.quad),
    });
  }

  let translateX = 0;
  let translateY = 0;

  if (animIn === "slideFromLeft") {
    translateX = interpolate(rel, [0, inDur], [-100, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
  } else if (animIn === "slideFromRight") {
    translateX = interpolate(rel, [0, inDur], [100, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
  } else if (animIn === "slideFromBottom") {
    translateY = interpolate(rel, [0, inDur], [100, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
  } else if (animIn === "slideFromTop") {
    translateY = interpolate(rel, [0, inDur], [-100, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
  }

  transform += ` translate(${translateX}px, ${translateY}px) scale(${currentScale})`;

  // 3. Typewriter: 글자 수 계산 + 커서
  const chars = Array.from(text); // 멀티바이트(한글/이모지) 안전 분리
  let displayText = text;
  let showCursor = false;
  if (animIn === "typewriter") {
    const visibleCount = Math.min(
      chars.length,
      Math.floor(
        interpolate(rel, [0, inDur], [0, chars.length], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      )
    );
    displayText = chars.slice(0, visibleCount).join("");
    // 타이핑 중에만 커서 표시, 8프레임 주기로 깜빡임
    showCursor = rel < inDur && Math.floor(rel / 8) % 2 === 0;
  }

  // 4. RevealMask: 왼→오른쪽 클립 마스크
  let clipPath: string | undefined;
  if (animIn === "revealMask") {
    const progress = interpolate(rel, [0, inDur], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: inEasingFn,
    });
    const rightClip = (1 - progress) * 100;
    clipPath = `inset(0 ${rightClip.toFixed(2)}% 0 0)`;
  }

  const cx = videoW / 2 + x;
  const cy = videoH / 2 + y;

  return (
    <div
      style={{
        position: "absolute",
        left: cx,
        top: cy,
        transform,
        opacity,
        clipPath,
        fontSize,
        fontFamily: "sans-serif, 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR'",
        color: textStyle.color || "#FFFFFF",
        fontWeight: String(textStyle.fontWeight || "bold"),
        textAlign: "center",
        whiteSpace: "pre-wrap",
        wordBreak: "keep-all",
        overflowWrap: "break-word",
        width,
        lineHeight: 1.25,
        letterSpacing: "0.02em",
        textShadow:
          textStyle.shadow || "2px 4px 16px rgba(0,0,0,0.85), 0 0 48px rgba(255,255,255,0.15)",
        background: textStyle.background || "transparent",
        padding: textStyle.backgroundPadding || "0px",
        borderRadius: textStyle.borderRadius || "0px",
        borderLeft: textStyle.borderLeft || "none",
        pointerEvents: "none",
        boxSizing: "border-box",
      }}
    >
      {displayText}
      {showCursor && <span style={{ opacity: 1 }}>|</span>}
    </div>
  );
};
