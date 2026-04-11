import React from "react";
import { Img, staticFile } from "remotion";
import { GlowTextFX } from "../components/fx/GlowTextFX";
import { SubtitleOverlay } from "../components/SubtitleOverlay";
import { PopupElement } from "../components/PopupElement";
import { GoldenRayFX } from "../components/fx/GoldenRayFX";
import { HighlighterFX } from "../components/fx/HighlighterFX";

interface Props {
  previewMode?: boolean;
}

export const Slide_p1: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <Img
        src={staticFile("image_1.jpeg")}
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
      src="image_1.jpeg"
      startFrame={0}
      durationFrames={954}
      width="100%"
      maxHeight="70%"
    />
    <HighlighterFX
      startFrame={0}
      durationFrames={954}
      x={-350}
      y={-200}
      fontSize={"80px"}
      highlightColor={"#FFE500"}
      textColor={"#1A1A1A"}
      text={"남의 쌀가마니 대신 보관"}
    />
    <GlowTextFX
      startFrame={485}
      durationFrames={469}
      x={-350}
      y={0}
      fontSize={"100px"}
      color={"#FFD700"}
      glowColor={"#FFD700"}
      text={"'우선 구매권'"}
    />
    <GoldenRayFX
      startFrame={485}
      durationFrames={469}
      x={200}
      y={100}
      rayCount={8}
      color={"#FFD700"}
    />
    {previewMode && (
      <SubtitleOverlay
        subtitles={[
          { startFrame: 0, endFrame: 128, text: "여러분, 동네 마트 창고에 남의 쌀가마니를" },
          { startFrame: 128, endFrame: 192, text: "대신 보관해 준다고 생각해 보세요" },
          { startFrame: 192, endFrame: 239, text: "창고 자리도 내어주고" },
          { startFrame: 239, endFrame: 290, text: "관리도 해주는 대신," },
          { startFrame: 290, endFrame: 342, text: "조건이 딱 하나 있습니다" },
          { startFrame: 342, endFrame: 393, text: "만약 동네에 기근이 들어" },
          { startFrame: 393, endFrame: 468, text: "쌀이 똑떨어지는 비상사태가 오면," },
          { startFrame: 468, endFrame: 517, text: "그 창고에 있는 쌀은" },
          { startFrame: 517, endFrame: 570, text: "다른 누구도 아닌 내가 가장" },
          { startFrame: 570, endFrame: 630, text: "먼저 돈을 내고 살 수 있는 권리" },
          { startFrame: 630, endFrame: 706, text: "이른바 '우선 구매권'을 갖는 거죠" },
          { startFrame: 706, endFrame: 754, text: "평소에는 주인이 그 쌀을" },
          { startFrame: 754, endFrame: 817, text: "자유롭게 사고팔아도 상관없지만," },
          { startFrame: 817, endFrame: 857, text: "위기 순간에는" },
          { startFrame: 857, endFrame: 902, text: "내 가족을 먹여 살릴" },
          { startFrame: 902, endFrame: 954, text: "확실한 보험이 되는 겁니다" },
        ]}
      />
    )}
  </div>
);
