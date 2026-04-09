import React from "react";
import { Composition } from "remotion";
import { VividComposition } from "./Composition";

/**
 * Root.tsx - Remotion 엔트리 포인트
 * 컴포지션 해상도/FPS/길이는 base_timeline.json 기반으로 Python이 설정합니다.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="VividOverlay"
        component={VividComposition}
        // Python 백엔드가 base_timeline.json 기반으로 아래 값을 주입합니다
        durationInFrames={1800}  // 기본값 60초@30fps
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          fxItems: [],
        }}
      />
    </>
  );
};
