import { CircleDashed } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="empty-state">
      <CircleDashed aria-hidden="true" size={22} />
      <div><h3>{title}</h3><p>{description}</p></div>
      {actions ? <div className="inline-actions">{actions}</div> : null}
    </div>
  );
}
