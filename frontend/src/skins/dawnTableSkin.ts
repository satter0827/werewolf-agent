import type { SkinDefinition } from "../gameClient/uiTypes";

export const dawnTableSkin: SkinDefinition = {
  id: "dawn_table",
  name: "夜明けの円卓",
  density: "comfortable",
  layout: {
    desktopColumns: "248px minmax(0, 1fr) 360px",
    mobileOrder: ["status", "table", "turn", "timeline"],
  },
  tokens: {
    accent: "#b8323a",
    dawn: "#e6a84f",
    forest: "#2f5d50",
    ink: "#201a16",
    parchment: "#fff6e4",
  },
};
