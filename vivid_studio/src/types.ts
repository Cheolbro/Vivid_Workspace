// VIVID Studio — 공유 타입 정의

export interface EffectProp {
  [key: string]: unknown;
}

/** commonProps: 위치/크기 공통 (x, y는 화면 중앙 기준 CENTER-RELATIVE) */
export interface EffectCommonProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fontSize?: string;
  [key: string]: unknown;
}

/** specificProps: FX별 고유 속성 (색상, 텍스트 스타일 등) */
export interface EffectSpecificProps {
  [key: string]: unknown;
}

export interface Effect {
  id: string;
  type: string; // "Popup" | "Video" | "TextPopup" | "Custom" | 컴포넌트명

  // 타이밍
  startFrame: number;
  durationFrames: number;

  // 최상위 단축 필드 (일부 플랜에서 사용)
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  zIndex?: number;

  // remotion_plan.json 실제 구조
  text?: string; // 텍스트 계열 FX 공통
  src?: string; // Popup/이미지 계열
  commonProps?: EffectCommonProps; // x, y (CENTER-RELATIVE), fontSize 등
  specificProps?: EffectSpecificProps; // FX별 고유 props (color, highlightColor 등)

  // 레거시 통합 props (하위 호환)
  props?: EffectProp;

  // 내부 메타 (FX 매칭 결과)
  _componentName?: string;
  _componentFile?: string;
}

// 비디오 실제 크기 (좌표 변환에 사용)
export const VIDEO_W = 1920;
export const VIDEO_H = 1080;

/** Effect 레이아웃 기본값 (type별, 절대 좌표) */
export const EFFECT_DEFAULTS: Record<string, Partial<Effect>> = {
  Popup: { x: 200, y: 200, width: 500, height: 300 },
  TextPopup: { x: 100, y: 800, width: 1720, height: 200 },
  Video: { x: 0, y: 0, width: 1920, height: 1080 },
  default: { x: 400, y: 300, width: 400, height: 240 },
};

/**
 * Effect에 레이아웃 기본값 보장.
 * commonProps.x/y는 CENTER-RELATIVE → 절대 좌표로 변환:
 *   absX = VIDEO_W/2 + commonProps.x
 *   absY = VIDEO_H/2 + commonProps.y
 */
export function withDefaults(
  eff: Effect
): Required<Pick<Effect, "x" | "y" | "width" | "height" | "zIndex">> & Effect {
  const defaults = EFFECT_DEFAULTS[eff.type] ?? EFFECT_DEFAULTS.default;

  // commonProps에서 절대 좌표 변환 (CENTER-RELATIVE → absolute px)
  const cpX = eff.commonProps?.x !== undefined ? VIDEO_W / 2 + eff.commonProps.x : undefined;
  const cpY = eff.commonProps?.y !== undefined ? VIDEO_H / 2 + eff.commonProps.y : undefined;
  const cpW = eff.commonProps?.width as number | undefined;
  const cpH = eff.commonProps?.height as number | undefined;

  // commonProps 절대 좌표가 있으면 최우선 적용, 없으면 eff 직접값, 없으면 defaults
  const resolvedX = cpX ?? eff.x ?? (defaults.x as number | undefined) ?? 400;
  const resolvedY = cpY ?? eff.y ?? (defaults.y as number | undefined) ?? 300;
  const resolvedW = cpW ?? eff.width ?? (defaults.width as number | undefined) ?? 400;
  const resolvedH = cpH ?? eff.height ?? (defaults.height as number | undefined) ?? 240;

  return {
    zIndex: 0,
    ...defaults,
    ...eff,
    x: resolvedX,
    y: resolvedY,
    width: resolvedW,
    height: resolvedH,
  };
}

export interface Slide {
  id: string;
  durationFrames: number;
  effects: Effect[];
  backgroundImage?: string;
  subtitle?: string;
}

export interface RemotionPlan {
  fps?: number;
  width?: number;
  height?: number;
  slides: Slide[];
  [key: string]: unknown;
}

// API 응답
export interface PlanPostResult {
  ok: boolean;
  backup: string;
}

export interface ServerStatus {
  ok: boolean;
  project_dir: string | null;
}

// 색상 prop 여부 판별 (key 이름 기반)
export function isColorProp(key: string): boolean {
  return /color|colour|fill|stroke|tint/i.test(key);
}

// 파일 경로 prop 여부 판별
export function isFileProp(key: string): boolean {
  return /path|src|url|file|image|video|asset/i.test(key);
}
