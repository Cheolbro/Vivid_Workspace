import React from "react";
import { Img, staticFile } from "remotion";
import { OilFillFX } from "../components/fx/OilFillFX";
import { SubtitleOverlay } from "../components/SubtitleOverlay";
import { TypewriterFX } from "../components/fx/TypewriterFX";
import { PopupElement } from "../components/PopupElement";
import { HighlighterFX } from "../components/fx/HighlighterFX";

interface Props {
  previewMode?: boolean;
}

export const Slide_p2: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <Img
        src={staticFile("image_2.jpeg")}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover" as const,
          opacity: 0.85,
        }}
      />
    )}
    <PopupElement
      src="image_2.jpeg"
      startFrame={0}
      durationFrames={754}
      width="100%"
      maxHeight="70%"
    />
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform: "scale(1.9625)",
        transformOrigin: "1017.0px 375.0px",
        zIndex: 0,
        pointerEvents: "none",
      }}
    >
      <TypewriterFX
        startFrame={45}
        durationFrames={709}
        x={57}
        y={-165}
        fontSize={"80px"}
        width={785}
        height={455}
        color={"#fff9bf"}
        speed={7}
        text={"국제 공동 비축"}
      />
    </div>
    <HighlighterFX
      startFrame={285}
      durationFrames={469}
      x={36}
      y={-348}
      fontSize={"80px"}
      highlightColor={"#FFE500"}
      textColor={"#1A1A1A"}
      text={"위기 시 가장 먼저!"}
    />
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform: "scale(0.6825)",
        transformOrigin: "1596.0px 758.0px",
        zIndex: 0,
        pointerEvents: "none",
      }}
    >
      <OilFillFX startFrame={45} durationFrames={709} x={636} y={218} width={273} height={478} />
    </div>
    {previewMode && (
      <SubtitleOverlay
        subtitles={[
          { startFrame: 0, endFrame: 1, text: "확실한 보험이 되는 겁니다" },
          { startFrame: 0, endFrame: 49, text: "국가 간의 원유 거래에도" },
          { startFrame: 49, endFrame: 99, text: "정확히 이런 제도가 있어요" },
          { startFrame: 99, endFrame: 195, text: "바로 '국제 공동 비축'이라는 제도입니다" },
          { startFrame: 195, endFrame: 261, text: "우리나라는 거대한 석유 비축기지를" },
          { startFrame: 261, endFrame: 314, text: "외국 석유 회사에 빌려주고," },
          { startFrame: 314, endFrame: 361, text: "나라에 비상이 걸리면" },
          { startFrame: 361, endFrame: 415, text: "그 기름을 우리가 가장 먼저" },
          { startFrame: 415, endFrame: 473, text: "살 수 있는 권리를 보장받습니다" },
          { startFrame: 473, endFrame: 510, text: "기름 한 방울 나지 않는" },
          { startFrame: 510, endFrame: 564, text: "대한민국 입장에서는," },
          { startFrame: 564, endFrame: 616, text: "우리 땅에 기름을 쌓아두고" },
          { startFrame: 616, endFrame: 665, text: "위기 시에 꺼내 쓸 수 있는" },
          { startFrame: 665, endFrame: 754, text: "가장 합리적이고 안전한 대안인 셈이죠" },
          { startFrame: 754, endFrame: 826, text: "그런데 여기서 한 가지 의문이 드실 거예요" },
        ]}
      />
    )}
  </div>
);
