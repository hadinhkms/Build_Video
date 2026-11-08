import "./index.css";
import React from "react";
import { Composition } from "remotion";
import { StoryComposition } from "./scenes/StoryComposition";
import { RenderPropsSchema, type RenderProps } from "./schemas/render-props";
import sample from "./fixtures/render_props.sample.json";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="StoryComposition"
    component={StoryComposition}
    schema={RenderPropsSchema}
    defaultProps={sample as RenderProps}
    durationInFrames={1}
    fps={24}
    width={1920}
    height={1080}
    calculateMetadata={({ props }) => ({
      durationInFrames: props.scenes.reduce((sum, s) => sum + s.durationInFrames, 0),
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
