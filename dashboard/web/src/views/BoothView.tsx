import { Header } from "../components/Header";
import { DegradedBanner } from "../components/DegradedBanner";
import { RiskPanel } from "../components/RiskPanel";
import { HardwareTwin } from "../components/HardwareTwin";
import { PipelineStrip } from "../components/PipelineStrip";
import { AlertFeed } from "../components/AlertFeed";

import "./booth.css";

// 1920x1080 TV, readable from 3m. A view, not a mode.
export default function BoothView() {
  return (
    <div className="booth">
      <Header />
      <DegradedBanner />
      <main className="booth-main">
        <section className="panel booth-risk"><span className="label">Risk</span><RiskPanel /></section>
        <section className="panel booth-twin"><span className="label">Hardware</span><HardwareTwin /></section>
        <section className="panel booth-pipe"><span className="label">Pipeline</span><PipelineStrip /></section>
        <section className="panel booth-feed"><span className="label">Latest alerts</span><AlertFeed /></section>
      </main>
    </div>
  );
}
