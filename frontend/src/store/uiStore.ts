import { create } from "zustand";

import { frontendSettings } from "../config";
import type { SkinId, ViewId } from "../gameClient/uiTypes";

interface UiStore {
  activeView: ViewId;
  activeGameId: string | null;
  manualPlayerId: string;
  skinId: SkinId;
  setActiveGameId: (gameId: string | null) => void;
  setActiveView: (view: ViewId) => void;
  setManualPlayerId: (playerId: string) => void;
}

export const useUiStore = create<UiStore>((set) => ({
  activeView: "setup",
  activeGameId: null,
  manualPlayerId: frontendSettings.defaultManualPlayerId,
  skinId: "dawn_table",
  setActiveGameId: (activeGameId) => set({ activeGameId }),
  setActiveView: (activeView) => set({ activeView }),
  setManualPlayerId: (manualPlayerId) => set({ manualPlayerId }),
}));
