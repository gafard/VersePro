import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { BACKEND_BASE, openExternal } from "../../env.js";
import { useStore } from "../../store.js";
export default function OfflineKit({ onConfigure }) {
  const [kit, setKit] = useState(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const listening = useStore((s) => s.isListening);
  useEffect(() => {
    api("offline-kit")
      .then(setKit)
      .catch((e) => setMessage(e.message));
  }, []);
  async function run(fn) {
    setBusy(true);
    setMessage("Traitement du kit… Vous pouvez patienter sur cette page.");
    try {
      await fn();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file) {
    if (!file) return;
    if (file.size > 1600000000) throw new Error("Kit limité à 1,6 Go.");
    const r = await fetch(`${BACKEND_BASE}/api/v1/offline-kit/import`, {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: file,
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Import impossible");
    setKit(await api("offline-kit"));
    setMessage(
      `${d.verified} fichier(s) vérifié(s), ${d.installed} installé(s). ${d.restart_required ? "Redémarrez VersePro hors direct pour charger les modèles." : "Les modèles étaient déjà présents."}`,
    );
  }
  return (
    <section className="service-panel">
      <h2>Préparer une fois, emporter partout</h2>
      <p>
        Créez un kit depuis cet ordinateur, puis importez-le sur un autre poste
        avec une clé USB. Il contient uniquement les modèles disponibles, sans
        Bible, clé d’accès ou données de culte.
      </p>
      <ul className="delivery-list">
        {kit?.files.map((f) => (
          <li key={f.name}>
            <span>{f.name.split("/").slice(-2).join(" / ")}</span>
            <strong>{Math.round(f.size / 1000000)} Mo</strong>
          </li>
        ))}
      </ul>
      {kit && !kit.files.length && (
        <p>
          Aucun modèle prêt à exporter. Commencez par préparer l’écoute locale.
        </p>
      )}
      <p>
        {kit
          ? `Taille des modèles : ${Math.round(kit.bytes / 1000000)} Mo.`
          : ""}
      </p>
      <div className="service-actions">
        <button
          className="primary"
          disabled={busy || listening || !kit?.files.length}
          onClick={() =>
            run(async () => {
              const d = await api("offline-kit/prepare-export", {});
              openExternal(`${BACKEND_BASE}${d.download}`);
              setMessage(
                "Kit prêt. Le téléchargement s’ouvre dans votre navigateur ; le lien est utilisable une fois pendant quinze minutes.",
              );
            })
          }
        >
          Créer le kit
        </button>
        <label className="service-file">
          Importer un kit
          <input
            type="file"
            accept=".zip"
            disabled={busy || listening}
            onChange={(e) => {
              const f = e.target.files[0];
              e.target.value = "";
              if (f) run(() => upload(f));
            }}
          />
        </label>
        <button disabled={busy} onClick={onConfigure}>
          Préparer les modèles
        </button>
      </div>
      <p role="status">{message}</p>
      <p>
        Utilisez un kit préparé par votre équipe. Les empreintes détectent les
        fichiers corrompus. Le moteur natif reste fourni par l’application ; le
        kit ne contient aucun exécutable.
      </p>
    </section>
  );
}
