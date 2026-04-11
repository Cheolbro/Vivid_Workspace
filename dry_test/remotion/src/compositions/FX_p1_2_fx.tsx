import React from "react";
import { GoldenRayFX } from "../components/fx/GoldenRayFX";

export const Comp_p1_2_fx: React.FC = () => (
  <div style={{ position: "relative", width: "100%", height: "100%", background: "transparent" }}>
    <GoldenRayFX startFrame={0} durationFrames={120} />
  </div>
);
