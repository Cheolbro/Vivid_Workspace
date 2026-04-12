import React from "react";
import { Img, staticFile } from "remotion";
import { SubtitleOverlay } from "../components/SubtitleOverlay";
import { UnderlineFX } from "../components/fx/UnderlineFX";
import { PopupElement } from "../components/PopupElement";
import { WarningFrameFX } from "../components/fx/WarningFrameFX";
import { OilLeakFX } from "../components/fx/OilLeakFX";
import { GlowTextFX } from "../components/fx/GlowTextFX";

interface Props {
  previewMode?: boolean;
}

export const Slide_p3: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <Img
        src={staticFile("image_3.jpeg")}
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
      src="image_3.jpeg"
      startFrame={0}
      durationFrames={817}
      width="100%"
      maxHeight="70%"
    />
    <WarningFrameFX
      startFrame={0}
      durationFrames={817}
      x={0}
      y={0}
      color={"rgba(220,0,0,0.55)"}
      blinkSpeed={1.6}
    />
    <UnderlineFX
      startFrame={185}
      durationFrames={632}
      x={350}
      y={-200}
      fontSize={"80px"}
      color={"#FFFFFF"}
      underlineColor={"#FF3333"}
      text={"90만 배럴 원유 강탈"}
    />
    <GlowTextFX
      startFrame={485}
      durationFrames={332}
      x={350}
      y={50}
      fontSize={"90px"}
      color={"#FFD700"}
      glowColor={"#FFD700"}
      text={"눈 뜨고 코 베인 진실"}
    />
    <OilLeakFX startFrame={185} durationFrames={632} x={-200} y={-100} />
    {previewMode && (
      <SubtitleOverlay
        subtitles={[
          { startFrame: 0, endFrame: 72, text: "그런데 여기서 한 가지 의문이 드실 거예요" },
          { startFrame: 72, endFrame: 109, text: "분명 우리 땅," },
          { startFrame: 109, endFrame: 181, text: "우리 비축기지에 보관 중이던 원유인데," },
          { startFrame: 181, endFrame: 259, text: "어떻게 하루아침에 90만 배럴이나 되는" },
          { startFrame: 259, endFrame: 313, text: "막대한 양을 눈 뜨고" },
          { startFrame: 313, endFrame: 377, text: "코 베이듯 뺏길 수 있냐는 거죠" },
          { startFrame: 377, endFrame: 436, text: "계약서에 우선 구매권이라는" },
          { startFrame: 436, endFrame: 512, text: "확실한 권리가 명시되어 있는데 말입니다" },
          { startFrame: 512, endFrame: 590, text: "이 서늘한 진실을 이해하시려면," },
          { startFrame: 590, endFrame: 668, text: "국제 자원 시장의 뼈저린 현실과" },
          { startFrame: 668, endFrame: 754, text: "2026년 2월 말에 벌어진" },
          { startFrame: 754, endFrame: 817, text: "사건의 전말을 들여다봐야 합니다" },
        ]}
      />
    )}
  </div>
);
