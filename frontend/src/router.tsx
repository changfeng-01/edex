import { createBrowserRouter, createMemoryRouter, Link, type RouteObject } from "react-router-dom";
import { ProductShell } from "./layouts/ProductShell";
import { AnalysisRunPage } from "./pages/AnalysisRunPage";
import { DemoPage } from "./pages/DemoPage";
import { DesignVersionPage } from "./pages/DesignVersionPage";
import { NewProjectPage } from "./pages/NewProjectPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { ProjectOverviewPage } from "./pages/ProjectOverviewPage";
function NotFound(){return <div className="not-found"><p className="eyebrow">404 / Route</p><h1>Page not found</h1><p>The requested workspace surface does not exist.</p><Link className="button button--primary" to="/workspaces/default/projects">Return to projects</Link></div>}
const routes:RouteObject[]=[{path:"/demo",element:<DemoPage/>},{path:"/",element:<DemoPage/>},{element:<ProductShell/>,children:[{path:"workspaces/:workspaceId/projects",element:<ProjectListPage/>},{path:"projects/new",element:<NewProjectPage/>},{path:"projects/:projectId/overview",element:<ProjectOverviewPage/>},{path:"projects/:projectId/versions/:versionId",element:<DesignVersionPage/>},{path:"analysis/:runId",element:<AnalysisRunPage/>},{path:"*",element:<NotFound/>}]}];
export function createAppRouter(initialEntries?:string[]){return initialEntries?createMemoryRouter(routes,{initialEntries}):createBrowserRouter(routes)}
