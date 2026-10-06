import type { ReactElement } from "react";

type PayloadView = (props: { payload: Record<string, unknown> }) => ReactElement | null;

function field(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

function MailView({ payload }: { payload: Record<string, unknown> }) {
  const channel = field(payload, "channel");
  if (channel === null) {
    return null;
  }
  return (
    <p>
      Канал почты: <strong>{channel}</strong>
    </p>
  );
}

function RecordsView({ payload }: { payload: Record<string, unknown> }) {
  const channel = field(payload, "channel");
  if (channel === null) {
    return null;
  }
  return (
    <p>
      Канал картотеки: <strong>{channel}</strong>
    </p>
  );
}

function ClerkView({ payload }: { payload: Record<string, unknown> }) {
  const role = field(payload, "role");
  if (role === null) {
    return null;
  }
  return (
    <p>
      Тестовая роль: <strong>{role}</strong>
    </p>
  );
}

const views: Record<string, PayloadView> = {
  mail: MailView,
  records: RecordsView,
  clerk: ClerkView,
};

export function RolePayload({
  roleId,
  payload,
}: {
  roleId: string | null;
  payload: Record<string, unknown> | null;
}) {
  if (roleId === null || payload === null) {
    return null;
  }
  const View = views[roleId];
  if (View === undefined) {
    return null;
  }
  return <View payload={payload} />;
}
