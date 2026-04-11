import React from "react";
import { TextPopupElement } from "../components/TextPopupElement";

export const Comp_p1_1_txt: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    <TextPopupElement
      text="남의 쌀가마니를 대신 보관?"
      startFrame={0}
      durationFrames={143}
      x={300}
      y={-250}
      fontSize="100px"
    />
  </div>
);
