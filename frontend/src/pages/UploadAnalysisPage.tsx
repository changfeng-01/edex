import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createProductClient, type ProductClient } from "../api/productClient";
import { type AnalysisContext, SimulationInputPanel } from "../components/product/SimulationInputPanel";
import { ErrorState } from "../components/product/ErrorState";
import { EvidenceSummary } from "../components/product/EvidenceSummary";
import { PageHeader } from "../components/product/PageHeader";
import { SectionPanel } from "../components/product/SectionPanel";
import type { ProductProject, Workspace } from "../types/product";

type ProjectMode = "existing" | "new";
let localWorkspaceInitialization: Promise<Workspace> | null = null;

function initializeLocalWorkspace(client: ProductClient) {
  if (!localWorkspaceInitialization) {
    localWorkspaceInitialization = client.createWorkspace("Local Workspace");
    void localWorkspaceInitialization.catch(() => { localWorkspaceInitialization = null; });
  }
  return localWorkspaceInitialization;
}

export function UploadAnalysisPage() {
  const client = useMemo(() => createProductClient(), []);
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [projects, setProjects] = useState<ProductProject[]>([]);
  const [projectMode, setProjectMode] = useState<ProjectMode>("existing");
  const [projectId, setProjectId] = useState("");
  const [projectName, setProjectName] = useState("");
  const [versionName, setVersionName] = useState("");
  const [loading, setLoading] = useState(true);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectLocked, setProjectLocked] = useState(false);
  const [contextLocked, setContextLocked] = useState(false);
  const [loadError, setLoadError] = useState<unknown>();
  const [validation, setValidation] = useState<Record<string, string>>({});
  const sessionProject = useRef<ProductProject | null>(null);

  useEffect(() => {
    let active = true;
    setProjectsLoading(true);
    async function load() {
      try {
        let next = await client.listWorkspaces();
        if (next.length === 0) next = [await initializeLocalWorkspace(client)];
        if (!active) return;
        setWorkspaces(next);
        if (next.length === 1) setWorkspaceId(next[0].workspace_id);
      } catch (error) {
        if (active) setLoadError(error);
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [client]);

  useEffect(() => {
    if (!workspaceId || projectLocked) return;
    let active = true;
    setProjects([]);
    setProjectId("");
    client.listProjects(workspaceId).then((next) => {
      if (!active) return;
      setProjects(next);
      if (next.length > 0) {
        setProjectMode("existing");
        setProjectId(next[0].project_id);
      } else {
        setProjectMode("new");
      }
    }).catch((error) => active && setLoadError(error)).finally(() => active && setProjectsLoading(false));
    return () => { active = false; };
  }, [client, workspaceId, projectLocked]);

  function validateContext() {
    const nextValidation: Record<string, string> = {};
    if (!workspaceId) nextValidation.workspace = "Workspace is required.";
    if (projectMode === "existing" && !projectId) nextValidation.project = "Project is required.";
    if (projectMode === "new" && !projectName.trim()) nextValidation.projectName = "Project name is required.";
    if (!versionName.trim()) nextValidation.versionName = "Design version name is required.";
    setValidation(nextValidation);
    return Object.keys(nextValidation).length === 0;
  }

  async function resolveContext(): Promise<AnalysisContext | null> {
    if (!validateContext()) return null;

    let selectedProject = sessionProject.current ?? projects.find((project) => project.project_id === projectId);
    if (!selectedProject && projectMode === "new") {
      selectedProject = await client.createProject({
        workspace_id: workspaceId,
        name: projectName.trim(),
        circuit_profile_id: "goa_8k",
        spec_revision_id: "spec_v1",
      });
      setProjects((current) => [...current, selectedProject as ProductProject]);
      setProjectId(selectedProject.project_id);
    }
    if (!selectedProject) return null;
    sessionProject.current = selectedProject;
    setProjectLocked(true);
    const version = await client.createDesignVersion(selectedProject.project_id, { label: versionName.trim() });
    return { versionId: version.design_version_id, circuitProfile: selectedProject.circuit_profile_id };
  }

  return (
    <>
      <PageHeader eyebrow="Evidence cockpit / Upload" title="Upload analysis" description="Create a versioned simulation context, validate its inputs, and open the resulting analysis run." />
      <EvidenceSummary />
      {loadError ? <ErrorState error={loadError} /> : null}
      <div className="upload-workflow" aria-busy={loading}>
        <SectionPanel title="1 · Analysis context" description="Workspace, project, and design version are persisted before preview and reused on retry.">
          <div className="context-form">
            <label>Workspace
              <select aria-label="Workspace" value={workspaceId} disabled={projectLocked || loading} onChange={(event) => { setWorkspaceId(event.target.value); setValidation({}); }}>
                <option value="">Select workspace</option>
                {workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}
              </select>
            </label>
            {validation.workspace ? <p className="field-error">{validation.workspace}</p> : null}

            {!projectsLoading && projects.length > 0 ? (
              <fieldset className="project-choice" disabled={projectLocked}>
                <legend>Project</legend>
                <label><input type="radio" name="project-mode" checked={projectMode === "existing"} onChange={() => setProjectMode("existing")} />Select existing</label>
                <label><input type="radio" name="project-mode" checked={projectMode === "new"} onChange={() => setProjectMode("new")} />Create new</label>
              </fieldset>
            ) : null}
            {projectsLoading ? <p className="muted">Loading projects…</p> : projectMode === "existing" && projects.length > 0 ? (
              <label>Existing project<select aria-label="Existing project" value={projectId} disabled={projectLocked} onChange={(event) => setProjectId(event.target.value)}>{projects.map((project) => <option key={project.project_id} value={project.project_id}>{project.name}</option>)}</select></label>
            ) : (
              <label>New project name<input aria-label="New project name" value={projectName} disabled={projectLocked} onChange={(event) => { setProjectName(event.target.value); setValidation((current) => ({ ...current, projectName: "" })); }} placeholder="e.g. 720-stage GOA" /></label>
            )}
            {validation.project ? <p className="field-error">{validation.project}</p> : null}
            {validation.projectName ? <p className="field-error">{validation.projectName}</p> : null}
            <div className="context-defaults"><span>Profile <code>goa_8k</code></span><span>Specification <code>spec_v1</code></span></div>
            <label>Design version name<input aria-label="Design version name" value={versionName} disabled={contextLocked} onChange={(event) => { setVersionName(event.target.value); setValidation((current) => ({ ...current, versionName: "" })); }} placeholder="e.g. baseline-2026-07" /></label>
            {validation.versionName ? <p className="field-error">{validation.versionName}</p> : null}
            {contextLocked ? <p className="context-lock">Context locked for this upload session. Preview retries will reuse the same design version.</p> : null}
          </div>
        </SectionPanel>
        <SectionPanel title="2 · Simulation inputs" description="Waveform CSV and parameter YAML are required. Netlist and plot images remain optional evidence attachments.">
          <SimulationInputPanel
            validateContext={validateContext}
            resolveContext={resolveContext}
            onContextLocked={() => setContextLocked(true)}
            onAnalysisCreated={(run) => navigate(`/analysis/${run.analysis_run_id}`)}
          />
        </SectionPanel>
      </div>
    </>
  );
}
