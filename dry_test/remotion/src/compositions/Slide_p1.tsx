import React from "react";
import { Img, staticFile } from "remotion";
import { GoldenRayFX } from "../components/fx/GoldenRayFX";
import { TextPopupElement } from "../components/TextPopupElement";
import { ImageElement } from "../components/ImageElement";

interface Props {
  previewMode?: boolean;
}

export const Slide_p1: React.FC<Props> = ({ previewMode = false }) => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    {previewMode && (
      <ImageElement
        src="image_1.jpeg"
        startFrame={0}
        durationFrames={954}
        width="100%"
        height="100%"
        kenBurns={{
          startScale: 1.1,
          endScale: 1.1,
          startX: -50,
          endX: 50,
          startY: 0,
          endY: 0,
          easing: "easeInOutSine",
        }}
      />
    )}
    <TextPopupElement
      text="남의 쌀가마니를
대신 보관"
      startFrame={0}
      durationFrames={954}
      x={-480}
      y={0}
      fontSize="110px"
      width="60%"
      textStyle={{
        color: "#000000",
        fontWeight: "900",
        shadow: "0 2px 15px rgba(255,255,255,0.8)",
        background: "rgba(255,255,255,0.4)",
        backgroundPadding: "15px 25px",
        borderRadius: "12px",
        borderLeft: "8px solid #FF4400",
      }}
      animation={{
        in: "slideFromLeft",
        inDurationFrames: 15,
        out: "fadeOut",
        outDurationFrames: 10,
        easing: "easeOutBack",
      }}
    />
    <GoldenRayFX
      startFrame={30}
      durationFrames={924}
      x={400}
      y={100}
      rayCount={12}
      particleCount={50}
      color={"#FFD700"}
      glowColor={"#FFF0A0"}
      spreadWidth={400}
    />
  </div>
);
