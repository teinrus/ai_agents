import type { ThreadSummary } from "./types";

export function ThreadList({
  summaries,
  activeId,
  waitingActive,
  busy,
  mobileOpen,
  onToggleMobile,
  onSelect,
  onNew,
}: {
  summaries: ThreadSummary[];
  activeId: string | null;
  waitingActive: boolean;
  busy: boolean;
  mobileOpen: boolean;
  onToggleMobile: () => void;
  onSelect: (threadId: string) => void;
  onNew: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-toolbar">
        <button type="button" onClick={onNew} disabled={busy}>
          Новый диалог
        </button>
        <button
          type="button"
          className="sidebar-toggle"
          aria-expanded={mobileOpen}
          aria-controls="thread-nav"
          onClick={onToggleMobile}
        >
          {mobileOpen ? "Скрыть диалоги" : "Показать диалоги"}
        </button>
      </div>
      <nav
        id="thread-nav"
        className={mobileOpen ? "thread-nav open" : "thread-nav"}
        aria-label="Диалоги"
      >
        {summaries.length === 0 ? <p className="muted">Нет сохранённых диалогов</p> : null}
        {summaries.map((row) => {
          const current = row.thread_id === activeId;
          const last = typeof row.last_text === "string" ? row.last_text.trim() : "";
          const title = last === "" ? "Пустой диалог" : last;
          return (
            <button
              key={row.thread_id}
              type="button"
              className="thread-item"
              aria-current={current ? true : undefined}
              disabled={busy}
              onClick={() => onSelect(row.thread_id)}
            >
              <span className="thread-title">{title}</span>
              <span className="thread-meta">
                {formatUpdatedAt(row.updated_at)} · {messageCountLabel(row.message_count)}
                {current && waitingActive ? (
                  <span className="waiting-mark"> ждёт решения</span>
                ) : null}
              </span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function formatUpdatedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) {
    return "только что";
  }
  if (minutes < 60) {
    return `${minutes} мин`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} ч`;
  }
  return date.toLocaleString("ru", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function messageCountLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return `${count} сообщение`;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} сообщения`;
  }
  return `${count} сообщений`;
}
