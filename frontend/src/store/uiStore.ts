import { create } from "zustand";

import type { SkinId, ViewId } from "../gameClient/uiTypes";

interface UiStore {
  activeView: ViewId;
  activeGameId: string;
  manualPlayerId: string;
  skinId: SkinId;
  setActiveGameId: (gameId: string) => void;
  setActiveView: (view: ViewId) => void;
  setManualPlayerId: (playerId: string) => void;
}

export const useUiStore = create<UiStore>((set) => ({
  activeView: "setup",
  activeGameId: "demo-game-1",
  manualPlayerId: "player-1",
  skinId: "dawn_table",
  setActiveGameId: (activeGameId) => set({ activeGameId }),
  setActiveView: (activeView) => set({ activeView }),
  setManualPlayerId: (manualPlayerId) => set({ manualPlayerId }),
}));
