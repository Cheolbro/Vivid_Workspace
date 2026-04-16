import React from "react";
import { AbsoluteFill } from "remotion";
import { PopupElement } from "@rfx/PopupElement";
import type { Effect } from "./types";
import { VIDEO_W, VIDEO_H } from "./types";

/**
 * FX 자동 레지스트리 (Vite Glob Import)
 * @rfx/fx/ 폴더 내 모든 .tsx 파일을 가져와 파일명을 키로 매핑.
 * Claude가 새 효과를 추가하면 코드 수정 없이 즉시 반영됩니다.
 */
const FX_MODULES = import.meta.glob("@rfx/fx/*.tsx", { eager: true });
const FX_REGISTRY: Record<string, React.ComponentType<any>> = {};

Object.entries(FX_MODULES).forEach(([path, mod]: [string, any]) => {
  // 파일 경로에서 컴포넌트 이름 추출 (예: .../GlowTextFX.tsx -> GlowTextFX)
  const name = path.split("/").pop()?.replace(".tsx", "");
  if (name && (mod[name] || mod.default)) {
    FX_REGISTRY[name] = mod[name] || mod.default;
  }
});
console.log("[DynamicSlide] FX_REGISTRY populated:", Object.keys(FX_REGISTRY));

export interface DynamicSlideProps {
  effects: Effect[];
}

// 이미지 src를 /api/asset/ 경로로 변환 (Remotion public 대신 FastAPI 서버에서 서빙)
function toAssetUrl(src: unknown): string {
  if (!src) return "";
  const s = String(src);
  if (s.startsWith("/") || s.startsWith("http")) return s;
  return `/api/asset/${s}`;
}

// 각 Effect를 type에 따라 적절한 FX 컴포넌트로 렌더링
// 데이터 구조: text/src(최상위), commonProps(x/y CENTER-RELATIVE + fontSize), specificProps(FX별 고유)
function renderEffect(eff: Effect, idx: number): React.ReactNode {
  // 타이밍 + 위치 공통 props
  // commonProps.x/y는 FX 컴포넌트 내부에서 width/2 + x 로 절대 위치 계산 → CENTER-RELATIVE 그대로 전달
  const common = {
    startFrame: eff.startFrame ?? 0,
    durationFrames: eff.durationFrames ?? 30,
    x: eff.commonProps?.x ?? eff.x ?? 0,
    y: eff.commonProps?.y ?? eff.y ?? 0,
  };

  // commonProps + specificProps 병합. specificProps가 동일 키 존재 시 우선.
  const merged = {
    ...(eff.commonProps ?? {}),
    ...(eff.specificProps ?? {}),
    ...(eff.props ?? {}), // 레거시 하위 호환
  } as Record<string, any>;

  // text: 최상위 eff.text 우선, 없으면 merged.text
  const text = eff.text ?? (merged.text as string | undefined) ?? "";
  // src: 최상위 eff.src 우선, 없으면 merged.src
  const src = toAssetUrl(eff.src ?? (merged.src as string | undefined) ?? "");

  // 1. 배경 이미지 자동 꽉 채움 (id에 _bg 포함 시만)
  // 이전: idx === 0 조건이 있어 첫 FX가 항상 배경으로 잘못 처리되는 버그 제거
  const isBg = Boolean(eff.id?.includes("_bg"));

  // 2. Responsive FX: 텍스트 계열 FX에 한해 height 기반 fontSize 자동 산출
  // 비텍스트 FX(GoldenRayFX 등)에 fontSize를 강제 주입하면 불필요한 prop 오염 발생
  const isTextFX = Boolean(text || merged.text);
  const cpHeight =
    typeof eff.commonProps?.height === "number"
      ? eff.commonProps.height
      : typeof eff.height === "number"
        ? eff.height
        : null;
  const hasFontSize = Boolean(merged.fontSize);
  if (isTextFX && cpHeight && !hasFontSize) {
    // height의 ~85%를 fontSize로 사용 (직관적인 크기 동기화)
    merged.fontSize = `${Math.round(cpHeight * 0.85)}px`;
  }

  // 3. FX 시각효과 크기 조절 (Global Scaling)
  const baselineW = 400;
  const currentW =
    typeof eff.commonProps?.width === "number"
      ? eff.commonProps.width
      : typeof eff.width === "number"
        ? eff.width
        : baselineW;
  const scale = currentW / baselineW;

  // FX 컴포넌트에 전달할 통합 props (text 포함)
  const withText = { ...common, text, ...merged };

  // FX 컴포넌트를 스케일 래퍼로 감싸는 함수
  const wrapFX = (Component: React.ComponentType<any>, props: any) => {
    const cx = VIDEO_W / 2 + (common.x as number);
    const cy = VIDEO_H / 2 + (common.y as number);
    return (
      <div
        key={eff.id ?? idx}
        style={{
          position: "absolute",
          inset: 0,
          transform: `scale(${scale})`,
          transformOrigin: `${cx}px ${cy}px`,
          zIndex: (eff.zIndex as number) ?? 0,
          pointerEvents: "none",
        }}
      >
        <Component {...props} />
      </div>
    );
  };

  // ── 렌더링 결정 (Dynamic Registry) ──
  const componentKey = eff.type === "Custom" ? eff._componentName || "" : eff.type;
  const FXComponent = FX_REGISTRY[componentKey];

  if (FXComponent) {
    // text 속성을 사용하는 FX인지 여부를 간단한 키워드 매칭 또는 type 명칭으로 추론 가능
    // 여기서는 withText를 기본으로 넘겨도 prop 타입에서 걸러지므로 안전함
    return wrapFX(FXComponent, withText);
  }

  // 폴백: Popup, PopupElement, Custom (일반 이미지/에셋 계열)
  if (["Popup", "PopupElement", "Custom"].includes(eff.type)) {
    return (
      <PopupElement
        key={eff.id ?? idx}
        startFrame={common.startFrame}
        durationFrames={common.durationFrames}
        x={common.x as number}
        y={common.y as number}
        src={src}
        width={isBg ? "100%" : (merged.width as string | undefined)}
        maxHeight={
          isBg
            ? "100%"
            : ((merged.height as string | undefined) ?? (merged.maxHeight as string | undefined))
        }
        // @ts-ignore
        objectFit={isBg ? "cover" : "contain"}
        style={{ zIndex: (eff.zIndex as number) ?? 0 }}
      />
    );
  }

  return null;
}

export const DynamicSlide: React.FC<DynamicSlideProps> = ({ effects }) => (
  <AbsoluteFill style={{ background: "transparent" }}>
    {effects.map((eff, idx) => renderEffect(eff, idx))}
  </AbsoluteFill>
);
