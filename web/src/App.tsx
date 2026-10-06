import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import {
  answerThreadConfirmation,
  listThreads,
  NotFoundError,
  openThread,
  readHealth,
  readThread,
  sendMessage,
} from "./api";
import { RoleStatus } from "./RoleStatus";
import { RunDetails } from "./RunDetails";
import { ThreadList } from "./ThreadList";
import type { Health, Thread, ThreadMessage, ThreadSummary } from "./types";

const THREAD_STORAGE_KEY = "ai-department.thread";

function emptyThread(threadId: string): Thread {
  return { thread_id: threadId, messages: [], run_ids: [], pending: null };
}

function persistThreadId(threadId: string): void {
  localStorage.setItem(THREAD_STORAGE_KEY, threadId);
}

function forgetThreadId(): void {
  localStorage.removeItem(THREAD_STORAGE_KEY);
}

export function App() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);
  const [summaries, setSummaries] = useState<ThreadSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  async function refreshSidebar(): Promise<void> {
    const [nextSummaries, nextHealth] = await Promise.all([listThreads(), readHealth()]);
    setSummaries(nextSummaries);
    setHealth(nextHealth);
  }

  useEffect(() => {
    let stopped = false;
    const boot = async () => {
      const stored = localStorage.getItem(THREAD_STORAGE_KEY);
      try {
        if (stored !== null) {
          try {
            const loaded = await readThread(stored);
            if (stopped) {
              return;
            }
            setThreadId(stored);
            setThread(loaded);
          } catch (exc) {
            if (!(exc instanceof NotFoundError)) {
              throw exc;
            }
            forgetThreadId();
            if (stopped) {
              return;
            }
            const id = await openThread();
            if (stopped) {
              return;
            }
            persistThreadId(id);
            setThreadId(id);
            setThread(emptyThread(id));
          }
        } else {
          const id = await openThread();
          if (stopped) {
            return;
          }
          persistThreadId(id);
          setThreadId(id);
          setThread(emptyThread(id));
        }
        if (stopped) {
          return;
        }
        const [nextSummaries, nextHealth] = await Promise.all([listThreads(), readHealth()]);
        if (stopped) {
          return;
        }
        setSummaries(nextSummaries);
        setHealth(nextHealth);
      } catch (exc: unknown) {
        if (!stopped) {
          setError(exc instanceof Error ? exc.message : "Не удалось открыть диалог");
        }
      }
    };
    void boot();
    return () => {
      stopped = true;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread?.messages.length, busy]);

  async function onSend() {
    const text = draft.trim();
    if (threadId === null || text === "" || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setDraft("");
    setThread((current) =>
      current === null
        ? current
        : {
            ...current,
            messages: [...current.messages, { author: "user", text, run_id: null, kind: null }],
          },
    );
    try {
      setThread(await sendMessage(threadId, text));
      await refreshSidebar();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Сообщение не отправлено");
    } finally {
      setBusy(false);
    }
  }

  async function onDecision(decision: "approve" | "reject") {
    if (threadId === null || thread?.pending === null || thread?.pending === undefined) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setThread(await answerThreadConfirmation(threadId, thread.pending.confirmation_id, decision));
      await refreshSidebar();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Решение не отправлено");
    } finally {
      setBusy(false);
    }
  }

  async function onNewDialog() {
    if (busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const id = await openThread();
      persistThreadId(id);
      setThreadId(id);
      setThread(emptyThread(id));
      setDraft("");
      setMobileOpen(false);
      await refreshSidebar();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Не удалось открыть диалог");
    } finally {
      setBusy(false);
    }
  }

  async function onSelectDialog(id: string) {
    if (busy || id === threadId) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const loaded = await readThread(id);
      persistThreadId(id);
      setThreadId(id);
      setThread(loaded);
      setMobileOpen(false);
      await refreshSidebar();
    } catch (exc) {
      if (exc instanceof NotFoundError) {
        forgetThreadId();
        setSummaries((rows) => rows.filter((row) => row.thread_id !== id));
        setError("Диалог не найден");
      } else {
        setError(exc instanceof Error ? exc.message : "Не удалось открыть диалог");
      }
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void onSend();
    }
  }

  const messages = thread?.messages ?? [];
  const pending = thread?.pending ?? null;

  return (
    <div className="shell">
      <header>
        <h1>Департамент</h1>
        <RoleStatus roles={health?.roles ?? []} />
      </header>
      <div className="workspace">
        <ThreadList
          summaries={summaries}
          activeId={threadId}
          waitingActive={pending !== null}
          busy={busy}
          mobileOpen={mobileOpen}
          onToggleMobile={() => setMobileOpen((value) => !value)}
          onSelect={(id) => void onSelectDialog(id)}
          onNew={() => void onNewDialog()}
        />
        <div className="chat">
          <main className="conversation" aria-live="polite">
            {messages.length === 0 ? (
              <p className="muted">
                Напишите, что нужно сделать. Например: «Посмотри непрочитанные письма и подготовь
                черновик ответа».
              </p>
            ) : null}
            {messages.map((message, index) => (
              <Bubble
                key={index}
                message={message}
                pendingHere={
                  pending !== null &&
                  message.run_id === pending.run_id &&
                  index === messages.length - 1
                }
                busy={busy}
                onDecision={(decision) => void onDecision(decision)}
              />
            ))}
            {busy ? <p className="muted typing">Департамент работает…</p> : null}
            <div ref={endRef} />
          </main>
          <footer className="composer">
            {error !== null ? <p className="error">{error}</p> : null}
            <div className="composer-row">
              <textarea
                value={draft}
                placeholder={
                  pending !== null
                    ? "Сначала разрешите или отклоните действие выше"
                    : "Сообщение департаменту"
                }
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
                disabled={threadId === null || busy}
                rows={2}
              />
              <button
                type="button"
                onClick={() => void onSend()}
                disabled={threadId === null || busy || draft.trim() === ""}
              >
                Отправить
              </button>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}

function Bubble({
  message,
  pendingHere,
  busy,
  onDecision,
}: {
  message: ThreadMessage;
  pendingHere: boolean;
  busy: boolean;
  onDecision: (decision: "approve" | "reject") => void;
}) {
  const [open, setOpen] = useState(false);
  const mine = message.author === "user";
  return (
    <article className={mine ? "bubble user" : `bubble assistant kind-${message.kind ?? "answer"}`}>
      <p className="bubble-text">{message.text}</p>
      {!mine && message.run_id !== null ? (
        <div className="bubble-meta">
          <span className="tag">{kindLabel(message.kind)}</span>
          <button type="button" className="link" onClick={() => setOpen((value) => !value)}>
            {open ? "Скрыть подробности" : "Подробности прогона"}
          </button>
        </div>
      ) : null}
      {open && message.run_id !== null ? <RunDetails runId={message.run_id} /> : null}
      {pendingHere ? (
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => onDecision("approve")}>
            Разрешить
          </button>
          <button type="button" disabled={busy} onClick={() => onDecision("reject")}>
            Отклонить
          </button>
        </div>
      ) : null}
    </article>
  );
}

function kindLabel(kind: string | null): string {
  switch (kind) {
    case "completed":
      return "выполнено";
    case "waiting_confirmation":
      return "нужно разрешение";
    case "no_role":
      return "нет сотрудника";
    case "rejected":
      return "не прошло оценку";
    case "failed":
      return "сбой";
    default:
      return "ответ";
  }
}
