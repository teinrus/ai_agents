import type { RoleHealth } from "./types";

function tone(state: string): "idle" | "waiting" | "active" | "quiet" {
  if (state === "Idle") {
    return "idle";
  }
  if (state === "WaitingConfirmation") {
    return "waiting";
  }
  if (state === "Failed" || state === "Retired") {
    return "quiet";
  }
  return "active";
}

export function RoleStatus({ roles }: { roles: RoleHealth[] }) {
  if (!Array.isArray(roles) || roles.length === 0) {
    return null;
  }
  return (
    <ul className="role-row" aria-label="Сотрудники">
      {roles.map((role) => (
        <li key={role.role_id}>
          <span className="role-badge" title={`${role.description} · ${role.state}`}>
            <span className={`role-dot ${tone(role.state)}`} aria-hidden="true" />
            {role.role_id}
          </span>
        </li>
      ))}
    </ul>
  );
}
