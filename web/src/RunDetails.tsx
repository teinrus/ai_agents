import { useEffect, useState } from "react";

import { readEvents, readRun } from "./api";
import { RolePayload } from "./roles/views";
import type { Envelope, Run } from "./types";

export function RunDetails({ runId }: { runId: string }) {
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Envelope[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    const load = async () => {
      try {
        const [nextRun, nextEvents] = await Promise.all([readRun(runId), readEvents(runId)]);
        if (!stopped) {
          setRun(nextRun);
          setEvents(nextEvents);
          setError(null);
        }
      } catch (exc) {
        if (!stopped) {
          setError(exc instanceof Error ? exc.message : "Не удалось прочитать прогон");
        }
      }
    };
    void load();
    return () => {
      stopped = true;
    };
  }, [runId]);

  if (error !== null) {
    return <p className="error">{error}</p>;
  }
  if (run === null) {
    return <p className="muted">Читаю ленту прогона…</p>;
  }
  const received = events.find((event) => event.event === "task.received");
  const domain = objectPayload(received?.payload.payload);
  const goal = typeof received?.payload.goal === "string" ? received.payload.goal : null;
  return (
    <div className="details">
      <p className="state">
        {run.role_id ?? "роль не выбрана"} · {run.state ?? "—"} · {run.status ?? "идёт"}
      </p>
      {goal !== null ? <p className="goal">Поручение: {goal}</p> : null}
      <p className="muted">
        Прогон {run.run_id.slice(0, 8)}. Шаги {run.step_count}, правки {run.revision_count}.
      </p>
      <RolePayload roleId={run.role_id} payload={domain} />
      {run.failure_reason !== null ? <p className="error">{run.failure_reason}</p> : null}
      <Routes events={events} />
      <Tools events={events} />
      <Evaluation events={events} />
    </div>
  );
}

function Routes({ events }: { events: Envelope[] }) {
  const routed = events.filter((event) => event.event === "model.routed");
  return (
    <section>
      <h2>Маршрут модели</h2>
      {routed.length === 0 ? <p>Маршрута не было.</p> : null}
      {routed.map((event) => (
        <article key={event.seq}>
          <p>
            seq {event.seq}: {String(event.payload.model_id ?? "нет модели")}
          </p>
          <Rejected items={event.payload.rejected} />
        </article>
      ))}
    </section>
  );
}

function Rejected({ items }: { items: unknown }) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }
  return (
    <ul>
      {items.map((item, index) => (
        <li key={index}>{formatRejected(item)}</li>
      ))}
    </ul>
  );
}

function Tools({ events }: { events: Envelope[] }) {
  const names = new Set([
    "tool.invoked",
    "tool.denied",
    "tool.confirmation_required",
    "tool.failed",
  ]);
  const tools = events.filter((event) => names.has(event.event));
  return (
    <section>
      <h2>Инструменты</h2>
      {tools.length === 0 ? <p>Вызовов не было.</p> : null}
      <ul>
        {tools.map((event) => (
          <li key={event.seq}>
            seq {event.seq}: {decisionLabel(event.event)} · {String(event.payload.tool ?? "")}
            {event.payload.rule !== undefined ? ` · правило ${String(event.payload.rule)}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Evaluation({ events }: { events: Envelope[] }) {
  const steps = events.filter((event) => event.event.startsWith("evaluation."));
  return (
    <section>
      <h2>Оценка</h2>
      {steps.length === 0 ? <p>Оценки не было.</p> : null}
      <ul>
        {steps.map((event) => (
          <li key={event.seq}>
            seq {event.seq}: {event.event}
            {event.payload.verdict !== undefined ? ` · ${String(event.payload.verdict)}` : ""}
            <Remarks checks={event.payload.checks} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Remarks({ checks }: { checks: unknown }) {
  if (!Array.isArray(checks)) {
    return null;
  }
  const failed = checks.filter((item) => {
    if (typeof item !== "object" || item === null) {
      return false;
    }
    const row = item as Record<string, unknown>;
    return row.passed === false && typeof row.remark === "string" && row.remark !== "";
  });
  if (failed.length === 0) {
    return null;
  }
  return (
    <ul>
      {failed.map((item, index) => {
        const row = item as Record<string, unknown>;
        return (
          <li key={index}>
            {String(row.name)}: {String(row.remark)}
          </li>
        );
      })}
    </ul>
  );
}

function decisionLabel(event: string): string {
  if (event === "tool.invoked") {
    return "allow";
  }
  if (event === "tool.confirmation_required") {
    return "confirm";
  }
  if (event === "tool.denied") {
    return "deny";
  }
  return "failed";
}

function objectPayload(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function formatRejected(item: unknown): string {
  if (typeof item !== "object" || item === null) {
    return String(item);
  }
  const row = item as Record<string, unknown>;
  const id = String(row.model_id ?? row.role_id ?? "");
  const reason = String(row.reason ?? row.score ?? "");
  return `${id} ${reason}`.trim();
}
