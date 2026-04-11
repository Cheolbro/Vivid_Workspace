import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { PopupElement } from "./components/PopupElement";

/**
 * Composition.tsx - 메인 타임라인 조립 파일
 * Python 백엔드가 remotion_plan.json을 읽어 이 파일을 자동 생성합니다.
 * 직접 편집하지 마세요 — main.py가 관리합니다.
 */

// Python이 주입하는 Props 타입 정의
interface FxItem {
  id: string;
  type: "Popup" | "Custom";
  src?: string;
  startFrame: number;
  durationFrames: number;
  x?: string;
  y?: string;
  width?: string;
  maxHeight?: string;
}

interface CompositionProps {
  fxItems?: FxItem[];
}

export const VividComposition: React.FC<CompositionProps> = ({ fxItems = [] }) => {
  return (
    // 배경 완전 투명 — remotion_spec.md 핵심 규칙
    <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
      {fxItems.map((item) => {
        if (item.type === "Popup" && item.src) {
          return (
            <PopupElement
              key={item.id}
              src={item.src}
              startFrame={item.startFrame}
              durationFrames={item.durationFrames}
              width={item.width}
              maxHeight={item.maxHeight}
            />
          );
        }
        // Custom FX는 Python이 동적으로 import 구문 추가
        return null;
      })}
    </div>
  );
};
