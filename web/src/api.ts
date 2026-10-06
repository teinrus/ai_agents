import type { Envelope, Health, Run, Thread, ThreadSummary } from "./types";

export class NotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotFoundError";
  }
}

export async function openThread(): Promise<string> {
  const response = await fetch("/threads", { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const body = (await response.json()) as { thread_id: string };
  return body.thread_id;
}

export async function readThread(threadId: string): Promise<Thread> {
  const response = await fetch(`/threads/${threadId}`);
  if (response.status === 404) {
    throw new NotFoundError(await errorText(response));
  }
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as Thread;
}

export async function listThreads(): Promise<ThreadSummary[]> {
  try {
    const response = await fetch("/threads");
    if (!response.ok) {
      return [];
    }
    const body: unknown = await response.json();
    return Array.isArray(body) ? (body as ThreadSummary[]) : [];
  } catch {
    return [];
  }
}

export async function readHealth(): Promise<Health | null> {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      return null;
    }
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      return null;
    }
    return body as Health;
  } catch {
    return null;
  }
}

export async function sendMessage(threadId: string, text: string): Promise<Thread> {
  const response = await fetch(`/threads/${threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as Thread;
}

export async function answerThreadConfirmation(
  threadId: string,
  confirmationId: string,
  decision: "approve" | "reject",
): Promise<Thread> {
  const response = await fetch(`/threads/${threadId}/confirmations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation_id: confirmationId, decision }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as Thread;
}

export async function readRun(runId: string): Promise<Run> {
  const response = await fetch(`/runs/${runId}`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as Run;
}

export async function readEvents(runId: string): Promise<Envelope[]> {
  const response = await fetch(`/runs/${runId}/events`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as Envelope[];
}

async function errorText(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: { message?: string } | string };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    return body.detail?.message ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}
