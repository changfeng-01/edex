import { FileText } from "lucide-react";

export function ArtifactList({ artifacts }: { artifacts: string[] }) {
  if (!artifacts.length) return <p className="muted">No artifacts indexed.</p>;
  return (
    <ul className="artifact-list">
      {artifacts.map((artifact) => (
        <li key={artifact} title={artifact}><FileText aria-hidden="true" size={15} /><span>{artifact}</span></li>
      ))}
    </ul>
  );
}
