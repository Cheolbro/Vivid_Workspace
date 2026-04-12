// VIVID Studio — 공유 타입 정의

export interface EffectProp {
  [key: string]: unknown;
}

export interface Effect {
  id: string;
  type: string; // "Popup" | "Video" | "TextPopup" | "Custom" | 컴포넌트명

  // 타이밍
  startFrame: number;
  durationFrames: number;

  // 레이아웃 (비디오 픽셀 기준: 1920×1080)
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  zIndex?: number;

  // 사용자 정의 props (FX별 상이)
  props?: EffectProp;

  // 내부 메타 (FX 매칭 결과)
  _componentName?: string;
  _componentFile?: string;
}

/** Effect 레이아웃 기본값 (type별) */
export const EFFECT_DEFAULTS: Record<string, Partial<Effect>> = {
  Popup: { x: 200, y: 200, width: 500, height: 300 },
  TextPopup: { x: 100, y: 800, width: 1720, height: 200 },
  Video: { x: 0, y: 0, width: 1920, height: 1080 },
  default: { x: 160, y: 160, width: 400, height: 240 },
};

/** Effect에 레이아웃 기본값 보장 */
export function withDefaults(
  eff: Effect
): Required<Pick<Effect, "x" | "y" | "width" | "height" | "zIndex">> & Effect {
  const defaults = EFFECT_DEFAULTS[eff.type] ?? EFFECT_DEFAULTS.default;
  return {
    x: 160,
    y: 160,
    width: 400,
    height: 240,
    zIndex: 0,
    ...defaults,
    ...eff,
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
