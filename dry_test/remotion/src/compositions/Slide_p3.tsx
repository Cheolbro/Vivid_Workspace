import React from "react";
import { Img, staticFile } from "remotion";
import { GritShakeFX } from "../components/fx/GritShakeFX";
import { TextPopupElement } from "../components/TextPopupElement";
import { ImageElement } from "../components/ImageElement";

interface Props {
  previewMode?: boolean;
}

export const Slide_p3: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <ImageElement
        src="image_3.jpeg"
        startFrame={0}
        durationFrames={817}
        width="100%"
        height="100%"
        kenBurns={{
          startScale: 1.0,
          endScale: 1.2,
          startX: 0,
          endX: 0,
          startY: 0,
          endY: 0,
          easing: "easeInOutSine",
        }}
      />
    )}
    <TextPopupElement
      text="눈 뜨고 코 베이듯
뺏길 수 있냐"
      startFrame={0}
      durationFrames={817}
      x={500}
      y={-200}
      fontSize="90px"
      width="55%"
      textStyle={{
        color: "#FFFFFF",
        fontWeight: "900",
        shadow: "0 10px 30px rgba(0,0,0,0.9)",
        background: "rgba(0,0,0,0.6)",
        backgroundPadding: "15px 30px",
        borderRadius: "4px",
        borderLeft: "10px solid #FF0000",
      }}
      animation={{
        in: "scaleUp",
        inDurationFrames: 12,
        out: "fadeOut",
        outDurationFrames: 12,
        easing: "easeOutBack",
      }}
    />
    <GritShakeFX
      startFrame={0}
      durationFrames={817}
      x={0}
      y={0}
      intensity={"high"}
      shakeAmplitude={8}
      noiseOpacity={0.2}
      vignetteIntensity={0.7}
      primaryColor={"#330000"}
      fadeInFrames={10}
    />
  </div>
);
