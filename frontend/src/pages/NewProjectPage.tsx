import { FormEvent, useState } from "react";
import { createProductClient } from "../api/productClient";
import { ErrorState } from "../components/product/ErrorState";
import { EvidenceSummary } from "../components/product/EvidenceSummary";
import { PageHeader } from "../components/product/PageHeader";
import { SectionPanel } from "../components/product/SectionPanel";

export function NewProjectPage() {
  const [name,setName]=useState(""); const [error,setError]=useState<unknown>(); const [validation,setValidation]=useState(""); const [created,setCreated]=useState(""); const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent){e.preventDefault(); if(!name.trim()){setValidation("Project name is required.");return;} setBusy(true);setError(undefined);try{const p=await createProductClient().createProject({workspace_id:"default",name:name.trim(),circuit_profile_id:"goa_8k",spec_revision_id:"spec_v1"});setCreated(p.project_id);}catch(err){setError(err);}finally{setBusy(false)}}
  return <><PageHeader eyebrow="Projects / New" title="Create GOA project" description="Start a versioned workspace without changing the simulation evidence boundary." /><EvidenceSummary />
    <SectionPanel title="Project definition"><form className="product-form" onSubmit={submit}><label>Project name<input aria-label="Project name" value={name} onChange={e=>{setName(e.target.value);setValidation("")}} placeholder="e.g. 720-stage GOA" /></label>{validation?<p className="field-error">{validation}</p>:null}<label>Circuit profile<select aria-label="Circuit profile" defaultValue="goa_8k"><option value="goa_8k">goa_8k</option></select></label><label>Specification revision<input value="spec_v1" readOnly /></label><button className="button button--primary" disabled={busy}>{busy?"Creating…":"Create project"}</button></form>{error?<ErrorState error={error}/>:null}{created?<p className="success-message">Project created: {created}</p>:null}</SectionPanel></>;
}
