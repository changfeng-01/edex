import { RouterProvider } from "react-router-dom";
import { createAppRouter } from "./router";
export default function App(){return <RouterProvider router={createAppRouter()} />}
