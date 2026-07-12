import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { createProductClient } from "../api/productClient";
import { ErrorState } from "../components/product/ErrorState";
import { LoadingSkeleton } from "../components/product/LoadingSkeleton";
import { PageHeader } from "../components/product/PageHeader";
import { SectionPanel } from "../components/product/SectionPanel";
export function ProjectOverviewPage(){const {projectId=""}=useParams();const [data,setData]=useState<Record<string,unknown>>();const [error,setError]=useState<unknown>();useEffect(()=>{createProductClient().getProjectOverview(projectId).then(setData).catch(setError)},[projectId]);return <><PageHeader eyebrow="Project" title="Project overview" description="Version lineage and analysis activity for this GOA design."/>{error?<ErrorState error={error}/>:!data?<LoadingSkeleton label="Loading project overview"/>:<SectionPanel title="Indexed workspace"><pre className="json-summary">{JSON.stringify(data,null,2)}</pre></SectionPanel>}</>}
