import React, { useEffect, useState } from "react";
import { useStore } from "../../store.js";
import { api, saveFile, servicePayload } from "./api.js";
const fresh = () => ({
  name: "Culte du dimanche",
  date: new Date().toLocaleDateString("en-CA"),
  notes: "",
  references: [],
  bible_version: "LSG",
  room_name: "",
  projection_theme: "presentation",
});
export default function PrepareService({ onLive }) {
  const [service, setService] = useState(() => {
    try {
      const saved = JSON.parse(
          localStorage.getItem("versepro_service_draft") || "{}",
        ),
        base = fresh();
      for (const key of Object.keys(base))
        if (typeof saved?.[key] === typeof base[key] && key !== "references")
          base[key] = saved[key];
      if (Array.isArray(saved?.references))
        base.references = saved.references
          .filter((r) => typeof r === "string")
          .slice(0, 100);
      return base;
    } catch {
      return fresh();
    }
  });
  const [saved, setSaved] = useState([]),
    [reference, setReference] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const isListening = useStore((s) => s.isListening),
    prepareReference = useStore((s) => s.prepareReference),
    updateSettings = useStore((s) => s.updateSettings);
  useEffect(() => {
    api("services")
      .then((d) => setSaved(d.services))
      .catch((e) => setMessage(e.message));
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("versepro_service_draft", JSON.stringify(service));
    } catch {
      setMessage(
        "Le brouillon ne peut pas être conservé sur cet appareil. Exportez le dossier.",
      );
    }
  }, [service]);
  const edit = (key, value) => setService((s) => ({ ...s, [key]: value }));
  async function run(action) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function extract() {
    const data = await api("bibles/extract_references", {
      text: service.notes,
    });
    edit(
      "references",
      [
        ...new Set([
          ...service.references,
          ...data.references.map((r) => r.reference),
        ]),
      ].slice(0, 100),
    );
    setMessage(`${data.count} référence(s) trouvée(s). Relisez le déroulé.`);
  }
  async function save() {
    const data = await api("services", servicePayload(service));
    setService(servicePayload(data));
    setSaved((s) => [data, ...s].slice(0, 100));
    setMessage("Dossier enregistré sur cet ordinateur.");
    return data;
  }
  async function loadFile(file) {
    if (!file) return;
    if (file.size > 1000000) throw new Error("Dossier limité à 1 Mo.");
    const raw = JSON.parse(await file.text());
    if (raw.format !== "versepro-service" || raw.schema_version !== 1)
      throw new Error("Ce format de dossier n’est pas pris en charge.");
    const data = await api("services", raw);
    setService(servicePayload(data));
    setSaved((s) => [data, ...s]);
    setMessage(
      "Dossier importé. Vérifiez les passages avant de les ajouter à la régie.",
    );
  }
  async function apply() {
    if (isListening)
      throw new Error("Arrêtez le micro avant de préparer un autre culte.");
    const data = await save();
    const settings = await updateSettings({
      bible_version: data.bible_version,
      projection_theme: data.projection_theme,
    });
    if (!settings) throw new Error("Le profil n’a pas pu être appliqué.");
    let count = 0;
    for (const ref of data.references) {
      if (await prepareReference(ref)) count++;
    }
    setMessage(
      `${count} passage(s) préparé(s) dans le déroulé. Les passages déjà présents sont conservés.`,
    );
  }
  return (
    <div className="service-layout">
      <section className="service-panel">
        <h2>Le dossier du culte</h2>
        <p>Préparez les passages, puis retrouvez-les dans votre régie.</p>
        <div className="service-fields">
          <label>
            Nom du culte
            <input
              value={service.name}
              maxLength={120}
              onChange={(e) => edit("name", e.target.value)}
            />
          </label>
          <label>
            Date
            <input
              type="date"
              value={service.date}
              onChange={(e) => edit("date", e.target.value)}
            />
          </label>
          <label>
            Salle
            <input
              placeholder="Temple principal"
              value={service.room_name}
              maxLength={120}
              onChange={(e) => edit("room_name", e.target.value)}
            />
          </label>
          <label>
            Traduction
            <input
              value={service.bible_version}
              maxLength={30}
              onChange={(e) =>
                edit("bible_version", e.target.value.toUpperCase())
              }
            />
          </label>
          <label>
            Habillage
            <select
              value={service.projection_theme}
              onChange={(e) => edit("projection_theme", e.target.value)}
            >
              <option value="presentation">Présentation</option>
              <option value="classic">Classique</option>
              <option value="minimal">Minimal</option>
              <option value="cinema">Cinéma</option>
              <option value="lower-third">Bandeau vidéo</option>
            </select>
          </label>
        </div>
        <label>
          Notes du prédicateur
          <textarea
            rows={6}
            maxLength={50000}
            value={service.notes}
            placeholder="Nous lirons Jean 3:16, puis Romains 8:28…"
            onChange={(e) => edit("notes", e.target.value)}
          />
        </label>
        <div className="service-actions">
          <button
            disabled={busy || !service.notes.trim()}
            onClick={() => run(extract)}
          >
            Retrouver les passages
          </button>
          <button disabled={busy} onClick={() => run(save)}>
            Enregistrer
          </button>
        </div>
        <p role="status">{message}</p>
      </section>
      <section className="service-panel">
        <h2>
          Votre déroulé <small>{service.references.length} passages</small>
        </h2>
        <form
          className="service-actions"
          onSubmit={(e) => {
            e.preventDefault();
            if (reference.trim()) {
              edit(
                "references",
                [...new Set([...service.references, reference.trim()])].slice(
                  0,
                  100,
                ),
              );
              setReference("");
            }
          }}
        >
          <input
            aria-label="Ajouter une référence"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            maxLength={200}
            placeholder="Jean 3:16"
          />
          <button disabled={!reference.trim()}>Ajouter</button>
        </form>
        <ol className="service-rundown">
          {service.references.map((ref, i) => (
            <li key={ref}>
              <span>{ref}</span>
              <div>
                <button
                  aria-label={`Monter ${ref}`}
                  disabled={i === 0}
                  onClick={() => {
                    const refs = [...service.references];
                    [refs[i - 1], refs[i]] = [refs[i], refs[i - 1]];
                    edit("references", refs);
                  }}
                >
                  ↑
                </button>
                <button
                  aria-label={`Retirer ${ref}`}
                  onClick={() =>
                    edit(
                      "references",
                      service.references.filter((r) => r !== ref),
                    )
                  }
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ol>
        {!service.references.length && (
          <p className="service-empty">
            Ajoutez une référence ou extrayez les passages de vos notes.
          </p>
        )}
        <div className="service-actions">
          <button
            className="primary"
            disabled={busy || isListening || !service.references.length}
            onClick={() => run(apply)}
          >
            Préparer la régie
          </button>
          <button onClick={onLive}>Ouvrir la régie</button>
        </div>
        <p>
          Le dossier partage les références et le profil. Les clés d’accès et
          les textes des Bibles restent sur leur ordinateur.
        </p>
        <div className="service-actions">
          <button
            disabled={busy}
            onClick={() =>
              run(async () => {
                const data = await save();
                saveFile("culte.versepro", servicePayload(data));
              })
            }
          >
            Exporter le dossier
          </button>
          <label className="service-file">
            Importer
            <input
              type="file"
              accept=".versepro,application/json"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files[0];
                e.target.value = "";
                run(() => loadFile(f));
              }}
            />
          </label>
        </div>
      </section>
      <section className="service-panel service-full">
        <h2>Dossiers enregistrés</h2>
        <div className="service-actions">
          {saved.map((s) => (
            <button key={s.id} onClick={() => setService(servicePayload(s))}>
              {s.name} · {s.date || "sans date"}
            </button>
          ))}
        </div>
        {!saved.length && (
          <p>Votre premier dossier apparaîtra ici après enregistrement.</p>
        )}
      </section>
    </div>
  );
}
