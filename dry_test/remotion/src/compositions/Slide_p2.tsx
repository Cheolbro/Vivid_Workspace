import React from "react";
import { Img, staticFile } from "remotion";
import { TextPopupElement } from "../components/TextPopupElement";
import { MetallicReflectionFX } from "../components/fx/MetallicReflectionFX";
import { ImageElement } from "../components/ImageElement";

interface Props {
  previewMode?: boolean;
}

export const Slide_p2: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <ImageElement
        src="image_2.jpeg"
        startFrame={0}
        durationFrames={754}
        width="100%"
        height="100%"
        kenBurns={{
          startScale: 1.2,
          endScale: 1.0,
          startX: 0,
          endX: 0,
          startY: 0,
          endY: 0,
          easing: "easeInOutSine",
        }}
      />
    )}
    <TextPopupElement
      text="국제 공동
비축 제도"
      startFrame={0}
      durationFrames={754}
      x={450}
      y={-320}
      fontSize="120px"
      width="50%"
      textStyle={{
        color: "#000000",
        fontWeight: "800",
        shadow: "0 4px 20px rgba(255,255,255,0.9)",
        background: "rgba(255,255,255,0.5)",
        backgroundPadding: "20px 30px",
        borderRadius: "8px",
      }}
      animation={{
        in: "fadeIn",
        inDurationFrames: 20,
        out: "fadeOut",
        outDurationFrames: 10,
        easing: "easeInOutSine",
      }}
    />
    <MetallicReflectionFX
      startFrame={30}
      durationFrames={724}
      x={0}
      y={0}
      primaryColor={"#FFFFFF"}
      intensity={"low"}
      direction={"rightward"}
      scale={1.2}
      opacity={0.4}
    />
  </div>
);
