import { lazy, Suspense, useEffect } from "react";
import { useStore } from "./store/store";
import { AuthGate } from "./components/AuthGate";
import { DevicesPanel } from "./components/DevicesPanel";
import OperatorView from "./views/OperatorView";

const BoothView = lazy(() => import("./views/BoothView"));
const DesignSpecimen = import.meta.env.DEV
  ? lazy(() => import("./views/DesignSpecimen"))
  : null;

function useView(): "operator" | "booth" {
  const params = new URLSearchParams(location.search);
  return params.get("view") === "booth" ? "booth" : "operator";
}

function Dashboard() {
  const view = useView();
  if (view === "booth") {
    return (
      <Suspense fallback={<div style={{ padding: 24 }} className="label">loading booth…</div>}>
        <BoothView />
      </Suspense>
    );
  }
  return <OperatorView />;
}

export default function App() {
  const band = useStore((s) => s.band);
  useEffect(() => { document.documentElement.setAttribute("data-band", band); }, [band]);

  if (DesignSpecimen && new URLSearchParams(location.search).has("design")) {
    return (
      <Suspense fallback={null}>
        <DesignSpecimen />
      </Suspense>
    );
  }

  return (
    <AuthGate>
      <Dashboard />
      <DevicesPanel />
    </AuthGate>
  );
}
