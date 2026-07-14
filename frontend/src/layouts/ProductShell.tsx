import { Activity, FolderKanban, Menu, Radio, UploadCloud, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

export function ProductShell() {
  const [open, setOpen] = useState(false);
  return <div className="product-shell">
    <button className="mobile-menu" aria-label={open ? "Close navigation" : "Open navigation"} onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
    <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
      <Link className="brand" to="/workspaces/default/projects"><Radio /><span>CircuitPilot<small>Evidence cockpit</small></span></Link>
      <nav aria-label="Product navigation">
        <NavLink to="/workspaces/default/projects" onClick={() => setOpen(false)}><FolderKanban />Projects</NavLink>
        <NavLink to="/upload" onClick={() => setOpen(false)}><UploadCloud />Upload analysis</NavLink>
        <NavLink to="/demo" onClick={() => setOpen(false)}><Activity />Public demo</NavLink>
      </nav>
      <div className="sidebar-note"><span>Phase 2</span><p>Manual simulation loop</p></div>
    </aside>
    {open ? <button className="nav-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} /> : null}
    <div className="shell-main"><div className="context-bar"><span>GOA workspace</span><code>default</code></div><main className="product-content"><Outlet /></main></div>
  </div>;
}
