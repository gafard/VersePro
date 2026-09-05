import React, { useState } from "react";
import { BACKEND_BASE, openExternal } from "../../env.js";
import { useStore } from "../../store.js";
import { api } from "./api.js";
export default function Discovery({ onConfigure, onPractice, onLive }) {
  const [completed, setCompleted] = useState(() => {
    try { return Boolean(localStorage.getItem('versepro_first_projection_at')) } catch { return false }
  });
  const [step, setStep] = useState(0),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const listening = useStore((s) => s.isListening),
    onAir = useStore((s) => s.onAir);
  async function project() {
    setBusy(true);
    try {
      const result = await api("discovery/project", {});
      if (!result.success) throw new Error("La projection n’a pas été acceptée.");
      useStore.setState({onAir: {reference: result.reference, text: result.text || '', at: new Date().toISOString()}});
      setStep(2);
      setCompleted(true);
      setMessage("Le passage a été envoyé. Regardez votre écran de sortie.");
      try {
        localStorage.setItem(
          "versepro_first_projection_at",
          new Date().toISOString(),
        );
      } catch {}
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (completed) return <section className="discovery-complete">
    <div><p className="service-kicker">PREMIÈRE PROJECTION RÉUSSIE</p><p>Préparez maintenant votre déroulé ou entraînez-vous avant le direct.</p></div>
    <div className="service-actions"><button onClick={onPractice}>Répéter</button><button onClick={onConfigure}>Configurer l’écoute</button><button onClick={() => setCompleted(false)}>Revoir la découverte</button></div>
  </section>;
  return (
    <section className="discovery">
      <div>
        <p className="service-kicker">VOTRE PREMIÈRE PROJECTION</p>
        <h2>
          Un passage.
          <br />
          Un écran. Vous avez la main.
        </h2>
        <p>
          Découvrez le geste de régie avant de configurer l’écoute automatique.
        </p>
        <div className="service-actions">
          <button
            className="primary"
            disabled={busy || listening || Boolean(onAir)}
            onClick={() => {
              openExternal(`${BACKEND_BASE}/output`);
              setStep(1);
            }}
          >
            1. Ouvrir l’écran
          </button>
          <button
            disabled={step < 1 || busy || listening || Boolean(onAir)}
            onClick={project}
          >
            2. Projeter Jean 3:16
          </button>
          {step >= 2 && <button onClick={onLive}>Aller à la régie</button>}
        </div>
        {(listening || onAir) && (
          <p>
            Un direct est actif. Utilisez la répétition pour essayer sans
            changer l’écran.
          </p>
        )}
        <p role="status">{message}</p>
      </div>
      <aside>
        <h3>Prêt pour la suite ?</h3>
        <button onClick={onPractice}>Répéter sans diffuser →</button>
        <button onClick={onConfigure}>Configurer l’écoute →</button>
        <p>
          Le mode local fonctionne sans Internet une fois ses modèles préparés.
        </p>
      </aside>
    </section>
  );
}
