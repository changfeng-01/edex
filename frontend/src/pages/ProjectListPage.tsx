import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import { EmptyState } from "../components/product/EmptyState";
import { ErrorState } from "../components/product/ErrorState";
import { LoadingSkeleton } from "../components/product/LoadingSkeleton";
import { PageHeader } from "../components/product/PageHeader";
import type { ProductProject } from "../types/product";

export function ProjectListPage() {
  const [projects, setProjects] = useState<ProductProject[] | null>(null); const [error, setError] = useState<unknown>();
  useEffect(() => { createProductClient().listProjects("default").then(setProjects).catch(setError); }, []);
  return <><PageHeader eyebrow="Workspace / default" title="Projects" description="GOA design histories, versioned inputs, and analysis evidence." action={<Link className="button button--primary" to="/projects/new">New project</Link>} />
    {error ? <ErrorState error={error} /> : projects === null ? <LoadingSkeleton label="Loading projects" /> : projects.length === 0 ? <EmptyState title="No GOA projects yet" description="Create a project to index versioned simulation evidence." actions={<><Link className="button button--primary" to="/projects/new">Create first project</Link><Link className="button" to="/demo">Open public demo</Link></>} /> : <div className="project-list">{projects.map(p => <Link aria-label={p.name} key={p.project_id} to={`/projects/${p.project_id}/overview`}><span><strong>{p.name}</strong><small title={p.project_id}>{p.project_id}</small></span><code>{p.circuit_profile_id}</code><span className="status status--ok">{p.status}</span></Link>)}</div>}
  </>;
}
