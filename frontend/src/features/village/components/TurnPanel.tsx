import { Eye, MessageSquareText } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type { TurnActionSubmit, TurnPanelModel } from "../../../gameClient/uiTypes";

interface TurnPanelProps {
  isSubmitting?: boolean;
  messageMaxChars?: number;
  onSubmit: (action: TurnActionSubmit) => void;
  panel: TurnPanelModel;
}

export function TurnPanel({
  isSubmitting = false,
  messageMaxChars = 200,
  onSubmit,
  panel,
}: TurnPanelProps) {
  const [selectedType, setSelectedType] = useState(panel.actions[0]?.type ?? "advance");
  const [message, setMessage] = useState("");
  const selectedAction = useMemo(
    () => panel.actions.find((action) => action.type === selectedType) ?? panel.actions[0],
    [panel.actions, selectedType],
  );
  const [targetId, setTargetId] = useState(selectedAction?.targetOptions[0]?.id ?? "");

  useEffect(() => {
    const nextAction = panel.actions[0];
    if (nextAction) {
      setSelectedType(nextAction.type);
      setTargetId(nextAction.targetOptions[0]?.id ?? "");
    }
  }, [panel.actions]);

  useEffect(() => {
    setTargetId(selectedAction?.targetOptions[0]?.id ?? "");
  }, [selectedAction]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedAction || isSubmitting) {
      return;
    }
    onSubmit({
      type: selectedAction.type,
      message: selectedAction.requiresMessage ? message : undefined,
      targetId: selectedAction.targetOptions.length > 0 ? targetId : undefined,
    });
    setMessage("");
  }

  return (
    <div className="wa-turn-panel">
      <p className="wa-kicker">あなたの手番</p>
      <h2>{panel.title}</h2>
      <p>{panel.subtitle}</p>
      <div className="wa-role-hint">
        <Eye size={18} aria-hidden="true" />
        <span>{panel.roleHint}</span>
      </div>
      <section className="wa-clue-list" aria-label="見えていること">
        <h3>見えていること</h3>
        {panel.visibleClues.map((clue) => (
          <div className="wa-clue" key={clue}>
            {clue}
          </div>
        ))}
      </section>
      <section className="wa-action-list" aria-label="できる行動">
        <h3>どう動く？</h3>
        {panel.actions.map((action) => (
          <button
            className={
              action.type === selectedType
                ? "wa-action-button wa-action-button-selected"
                : "wa-action-button"
            }
            disabled={!action.enabled || isSubmitting}
            key={action.type}
            onClick={() => setSelectedType(action.type)}
            type="button"
          >
            <MessageSquareText size={18} aria-hidden="true" />
            <span>
              <strong>{action.label}</strong>
              <small>{action.description}</small>
            </span>
          </button>
        ))}
      </section>
      {selectedAction ? (
        <form className="wa-action-form" onSubmit={handleSubmit}>
          {selectedAction.requiresMessage ? (
            <label>
              ひとこと
              <textarea
                maxLength={messageMaxChars}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="参加者へ伝えること"
                value={message}
              />
            </label>
          ) : null}
          {selectedAction.targetOptions.length > 0 ? (
            <label>
              相手を選ぶ
              <select onChange={(event) => setTargetId(event.target.value)} value={targetId}>
                {selectedAction.targetOptions.map((target) => (
                  <option key={target.id} value={target.id}>
                    {target.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            className="wa-primary-action"
            disabled={
              isSubmitting ||
              (selectedAction.requiresMessage && message.trim().length === 0) ||
              (selectedAction.targetOptions.length > 0 && targetId.length === 0)
            }
            type="submit"
          >
            {isSubmitting ? "送信中" : selectedAction.type === "advance" ? "進める" : "決定する"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
