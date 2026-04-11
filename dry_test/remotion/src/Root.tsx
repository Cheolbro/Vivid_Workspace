import React from "react";
import { Composition } from "remotion";
import { Slide_p1 } from "./compositions/Slide_p1";
import { Slide_p2 } from "./compositions/Slide_p2";
import { Slide_p3 } from "./compositions/Slide_p3";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="VividSlide-p1"
      component={Slide_p1}
      durationInFrames={954}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ previewMode: true }}
    />
    <Composition
      id="VividSlide-p2"
      component={Slide_p2}
      durationInFrames={754}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ previewMode: true }}
    />
    <Composition
      id="VividSlide-p3"
      component={Slide_p3}
      durationInFrames={817}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ previewMode: true }}
    />
  </>
);
