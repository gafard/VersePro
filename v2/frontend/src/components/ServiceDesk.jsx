import React, { lazy, Suspense, useState } from "react";
import Discovery from "./preparation/Discovery.jsx";
import PrepareService from "./preparation/PrepareService.jsx";
import "./preparation/service-desk.css";
const Rehearsal = lazy(() => import("./preparation/Rehearsal.jsx"));
const OutputsPanel = lazy(() => import("./preparation/OutputsPanel.jsx"));
const OfflineKit = lazy(() => import("./preparation/OfflineKit.jsx"));
const tabs = [
  ["prepare", "Préparer"],
  ["practice", "Répéter"],
  ["outputs", "Écrans"],
  ["kit", "Kit hors ligne"],
];
export default function ServiceDesk({
  onConfigure,
  onLive,
  initialTab = "prepare",
}) {
  const [tab, setTab] = useState(initialTab);
  return (
    <div className="service-desk">
      <div className="service-intro">
        <div>
          <p className="service-kicker">AVANT LE DIRECT</p>
          <h1>Votre prochain culte commence ici.</h1>
        </div>
        <button onClick={onLive}>Ouvrir la régie →</button>
      </div>
      <nav className="service-tabs" aria-label="Préparation du culte">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "prepare" && (
        <>
          <Discovery
            onConfigure={onConfigure}
            onPractice={() => setTab("practice")}
            onLive={onLive}
          />
          <PrepareService onLive={onLive} />
        </>
      )}
      <Suspense fallback={<p role="status">Ouverture…</p>}>
        {tab === "practice" && <Rehearsal onConfigure={onConfigure} />}{" "}
        {tab === "outputs" && <OutputsPanel />}
        {tab === "kit" && <OfflineKit onConfigure={onConfigure} />}
      </Suspense>
    </div>
  );
}
