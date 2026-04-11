import React from "react";
import { TextPopupElement } from "../components/TextPopupElement";

export const Comp_p1_3_txt: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    <TextPopupElement
      text="'우선 구매권'"
      startFrame={0}
      durationFrames={150}
      x={0}
      y={-350}
      fontSize="120px"
    />
  </div>
);
