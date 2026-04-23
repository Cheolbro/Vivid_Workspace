import React from "react";
import { Generic3DAssetFX } from "./Generic3DAssetFX";

export const PassengerPlane3DFX: React.FC<any> = (props) => {
  return <Generic3DAssetFX {...props} assetName="passenger_plane.png" />;
};
