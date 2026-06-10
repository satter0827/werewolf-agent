import { BookOpen, CircleDot, Eye, ScrollText, type LucideIcon } from "lucide-react";

import type { ViewId } from "../../../gameClient/uiTypes";

const navItems: Array<{ id: ViewId; label: string; icon: LucideIcon }> = [
  { id: "setup", label: "村を作る", icon: CircleDot },
  { id: "play", label: "プレイ", icon: ScrollText },
  { id: "observe", label: "観戦", icon: Eye },
  { id: "records", label: "記録", icon: BookOpen },
];

interface VillageNavProps {
  activeView: ViewId;
  onNavigate: (view: ViewId) => void;
}

export function VillageNav({ activeView, onNavigate }: VillageNavProps) {
  return (
    <aside className="wa-nav" aria-label="村の案内">
      <div className="wa-brand">
        <div className="wa-brand-mark">W</div>
        <div>
          <strong>Werewolf Agent</strong>
          <span>夜明けの円卓</span>
        </div>
      </div>
      <nav className="wa-nav-list">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={item.id === activeView ? "wa-nav-button wa-nav-active" : "wa-nav-button"}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              type="button"
            >
              <Icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="wa-nav-note">
        <span>今夜の村</span>
        <strong>霧の村</strong>
        <p>公開された出来事だけを手がかりに、朝まで生き残りましょう。</p>
      </div>
    </aside>
  );
}
