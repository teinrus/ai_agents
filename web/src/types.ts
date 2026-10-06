export type Envelope = {
  seq: number;
  event: string;
  level: string;
  message: string;
  role_id: string | null;
  payload: Record<string, unknown>;
};

export type Pending = {
  confirmation_id: string;
  tool: string;
  arguments: Record<string, unknown>;
};

export type Run = {
  run_id: string;
  correlation_id: string;
  status: string | null;
  state: string | null;
  role_id: string | null;
  failure_reason: string | null;
  pending_confirmation: Pending | null;
  step_count: number;
  revision_count: number;
  output: unknown;
};

export type ThreadMessage = {
  author: "user" | "assistant";
  text: string;
  run_id: string | null;
  kind: string | null;
};

export type ThreadPending = Pending & {
  run_id: string;
};

export type Thread = {
  thread_id: string;
  messages: ThreadMessage[];
  run_ids: string[];
  pending: ThreadPending | null;
};
