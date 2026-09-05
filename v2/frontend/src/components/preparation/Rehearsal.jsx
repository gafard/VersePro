import { rehearsalResults } from './rehearsal-events.js';
import React, { useEffect, useRef, useState } from "react";
import { useStore } from "../../store.js";
import { BACKEND_BASE, BACKEND_WS_BASE } from "../../env.js";
import { api, saveFile } from "./api.js";

export default function Rehearsal({ onConfigure }) {
  const [demo, setDemo] = useState(null),
    [step, setStep] = useState(0),
    [result, setResult] = useState(null),
    [screen, setScreen] = useState(null),
    [events, setEvents] = useState([]),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [partial, setPartial] = useState(""),
    [file, setFile] = useState(null),
    [source, setSource] = useState("guided"),
    [audioUrl, setAudioUrl] = useState("");
  const wsRef = useRef(null),
    started = useRef(0),
    arrival = useRef(0),
    runId = useRef(0),
    timerRef = useRef(null);
  const [correction, setCorrection] = useState("");
  const listening = useStore((s) => s.isListening);
  useEffect(() => {
    let active = true;
    api("rehearsal/demo")
      .then((d) => {
        if (active) setDemo(d);
      })
      .catch((e) => {
        if (active) setMessage(e.message);
      });
    return () => {
      active = false;
      runId.current++;
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, []);
  useEffect(() => {
    let alive = true,
      url;
    fetch(`${BACKEND_BASE}/api/v1/rehearsal/demo.wav`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.blob();
      })
      .then((b) => {
        url = URL.createObjectURL(b);
        if (alive) setAudioUrl(url);
        else URL.revokeObjectURL(url);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, []);
  function stop() {
    runId.current++;
    clearTimeout(timerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    setBusy(false);
    setPartial("");
  }
  function reset() {
    stop();
    setEvents([]);
    setResult(null);
    setScreen(null);
    setStep(0);
    setMessage("Nouvelle répétition. Les écrans du direct restent isolés.");
    setSource("guided");
  }
  async function next() {
    if (!demo || step >= demo.lines.length) return;
    setBusy(true);
    setSource("guided");
    setMessage("");
    const id = ++runId.current;
    try {
      const data = await api("rehearsal/detect", {
        text: demo.lines[step].text,
      });
      if (id !== runId.current) return;
      setResult(data);
      arrival.current = performance.now();
      setEvents((e) => [
        ...e,
        {
          ...data,
          expected: demo.lines[step].expected,
          action: "proposé",
          source: "guided",
        },
      ]);
      setStep((s) => s + 1);
    } catch (e) {
      setMessage(e.message);
    } finally {
      if (id === runId.current) setBusy(false);
    }
  }
  function act(action) {
    if (!result) return;
    const delay = Math.round(performance.now() - arrival.current);
    setEvents((e) => [
      ...e,
      {
        reference: result.candidate?.reference || null,
        action,
        reaction_ms: delay,
        source,
      },
    ]);
    if (action === "validé") setScreen(result.candidate);
    setResult(null);
  }
  async function audio() {
    stop();
    const id = runId.current;
    setBusy(true);
    setSource("audio");
    setMessage("Préparation de l’audio…");
    setEvents([]);
    setScreen(null);
    setResult(null);
    try {
      const bytes = file
        ? await file.arrayBuffer()
        : await fetch(`${BACKEND_BASE}/api/v1/rehearsal/demo.wav`).then((r) => {
            if (!r.ok) throw new Error("Audio indisponible");
            return r.arrayBuffer();
          });
      if (bytes.byteLength > 60000000)
        throw new Error("Choisissez un extrait de 60 Mo maximum.");
      const ctx = new AudioContext();
      let decoded;
      try {
        decoded = await ctx.decodeAudioData(bytes);
      } finally {
        await ctx.close();
      }
      if (decoded.duration > 600)
        throw new Error("Choisissez un extrait de dix minutes maximum.");
      const offline = new OfflineAudioContext(
          1,
          Math.ceil(decoded.duration * 16000),
          16000,
        ),
        input = offline.createBufferSource();
      input.buffer = decoded;
      input.connect(offline.destination);
      input.start();
      const converted = (await offline.startRendering()).getChannelData(0);
      const pcm = new Int16Array(converted.length);
      for (let i = 0; i < converted.length; i++)
        pcm[i] = Math.max(
          -32768,
          Math.min(32767, Math.round(converted[i] * 32767)),
        );
      if (id !== runId.current) return;
      const base =
        BACKEND_WS_BASE ||
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
      const ws = new WebSocket(`${base}/ws/rehearsal`);
      wsRef.current = ws;
      let position = 0,
        finished = false;
      started.current = performance.now();
      ws.onmessage = (e) => {
        if (id !== runId.current) return;
        const d = JSON.parse(e.data);
        if (d.type === "ready") {
          setPartial(d.partial || "");
          setMessage(
            `Écoute locale · ${Math.round(d.audio_seconds || 0)} s analysées`,
          );
          if (position < pcm.length) {
            const end = Math.min(position + 8000, pcm.length);
            ws.send(pcm.slice(position, end).buffer);
            position = end;
          } else if (!finished) {
            finished = true;
            ws.send("finish");
          }
        }
        if (d.type === "result") {
          const results = rehearsalResults(d);
          if (results.length) {
            arrival.current = performance.now();
            setResult(results[0]);
            setEvents((rows) => [
              ...rows,
              ...results.map(result => ({ ...result, action: "proposé", source: "audio" })),
            ]);
          }
        }
        if (d.type === "error") {
          setMessage(d.message);
          setBusy(false);
        }
        if (d.type === "done") {
          setBusy(false);
          setPartial("");
          setMessage(
            `${Math.round(d.audio_seconds)} s d’audio analysées en ${d.processing_seconds} s. Ce traitement de fichier ne mesure pas la latence d’un culte en direct.`,
          );
        }
      };
      ws.onerror = () => {
        if (id === runId.current) {
          setMessage("La connexion de répétition a échoué.");
          setBusy(false);
        }
      };
      ws.onclose = () => {
        if (id === runId.current) setBusy(false);
      };
    } catch (e) {
      if (id === runId.current) {
        setMessage(e.message);
        setBusy(false);
      }
    }
  }
  return (
    <>
      <div className="service-intro">
        <div>
          <h2>Répéter mon dimanche</h2>
          <p>
            Votre espace d’entraînement. Aucune action de cette page n’est
            envoyée à la salle.
          </p>
        </div>
        <button onClick={reset}>Recommencer</button>
      </div>
      <div className="service-layout">
        <section className="service-panel">
          <h3>Exercice guidé</h3>
          <p>
            Quatre phrases connues, analysées par le moteur biblique. Cet
            exercice entraîne votre geste ; il ne teste pas la reconnaissance
            vocale.
          </p>
          <button
            className="primary"
            disabled={busy || !demo || step >= demo.lines.length}
            onClick={next}
          >
            {step
              ? `Phrase suivante (${Math.min(step + 1, 4)}/4)`
              : "Commencer l’exercice"}
          </button>
          <hr />
          <h3>Éprouver l’écoute locale</h3>
          <p>
            Analysez l’audio inclus, ou un extrait choisi sur cet ordinateur. Le
            moteur Nemotron doit être prêt.
          </p>
          {audioUrl && <audio controls preload="none" src={audioUrl} />}
          <small>
            Exemple inclus : voix de synthèse française, sans enregistrement de
            culte.
          </small>
          <label>
            Votre extrait audio
            <input
              type="file"
              accept="audio/*"
              disabled={busy}
              onChange={(e) => setFile(e.target.files[0] || null)}
            />
          </label>
          <div className="service-actions">
            <button disabled={busy || listening} onClick={audio}>
              Analyser {file ? "mon extrait" : "l’exemple"}
            </button>
            {busy && <button onClick={stop}>Arrêter</button>}
            <button onClick={onConfigure}>Préparer le moteur</button>
          </div>
          {listening && <p>Arrêtez le micro du direct avant le test audio.</p>}
          <p role="status">{message}</p>
          {partial && <p className="service-partial">{partial}</p>}
        </section>
        <section className="service-panel">
          <h3>À vous de décider</h3>
          {result ? (
            <>
              <blockquote>{result.text}</blockquote>
              {result.candidate ? (
                <>
                  <h2>{result.candidate.reference}</h2>
                  <p>
                    {result.candidate.text ||
                      "Référence incomplète : précisez le verset avant de valider."}
                  </p>
                  <small>
                    {result.candidate.explanation ||
                      "Proposition à vérifier dans la répétition."}
                  </small>
                  <div className="service-actions">
                    <button
                      className="primary"
                      disabled={!result.candidate.text}
                      onClick={() => act("validé")}
                    >
                      Valider pour l’exercice
                    </button>
                    <button onClick={() => act("ignoré")}>Ignorer</button>
                  </div>
                </>
              ) : (
                <>
                  <p>
                    Aucun passage proposé. Les annonces ordinaires ne doivent
                    pas devenir des versets.
                  </p>
                  <button onClick={() => act("abstention")}>Continuer</button>
                </>
              )}
            </>
          ) : (
            <p className="service-empty">
              Les propositions de l’exercice apparaîtront ici.
            </p>
          )}
          {result && (
            <form
              className="service-actions"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const d = await api("learning/corrections", {
                    text: result.text.slice(0, 1000),
                    reference: correction,
                  });
                  setMessage(
                    `Correction mémorisée : ${d.reference}. Elle ne s’applique qu’à cette phrase et reste à valider.`,
                  );
                  setCorrection("");
                } catch (e) {
                  setMessage(e.message);
                }
              }}
            >
              <input
                aria-label="Référence corrigée"
                placeholder="Corriger : Jean 3:16"
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                maxLength={200}
              />
              <button disabled={!correction.trim()}>Mémoriser</button>
            </form>
          )}
          <div className="practice-screen" aria-live="polite">
            <small>ÉCRAN DE RÉPÉTITION · ISOLÉ</small>
            <h3>{screen?.reference || "Aucun passage"}</h3>
            <p>
              {screen?.text || "Validez une proposition pour voir le résultat."}
            </p>
          </div>
          <button
            disabled={!screen}
            onClick={() => {
              setScreen(null);
              setEvents((e) => [...e, { action: "écran effacé", source }]);
            }}
          >
            Effacer l’exercice
          </button>
        </section>
        <section className="service-panel service-full">
          <h3>Votre bilan</h3>
          <p>
            {events.filter((e) => e.action === "validé").length} validations ·{" "}
            {events.filter((e) => e.action === "ignoré").length} propositions
            ignorées · {events.filter((e) => e.action === "proposé").length}{" "}
            résultats à relire
          </p>
          <ol className="practice-events">
            {events
              .filter((e) => e.action === "proposé")
              .map((e, i) => (
                <li key={i}>
                  <span>{e.text}</span>
                  <button
                    onClick={() => {
                      setResult(e);
                      arrival.current = performance.now();
                    }}
                  >
                    {e.candidate?.reference || "Aucune proposition"}
                  </button>
                  {e.source === "guided" && (
                    <small>Attendu : {e.expected || "aucun verset"}</small>
                  )}
                </li>
              ))}
          </ol>
          <div className="service-actions">
            <button
              disabled={!events.length}
              onClick={() =>
                saveFile("bilan-repetition.json", {
                  format: "versepro-rehearsal",
                  schema_version: 1,
                  date: new Date().toISOString(),
                  events,
                })
              }
            >
              Exporter le bilan
            </button>
          </div>
          <button
            onClick={async () => {
              try {
                saveFile(
                  "corrections-versepro.json",
                  await api("learning/corrections"),
                );
              } catch (e) {
                setMessage(e.message);
              }
            }}
          >
            Exporter les corrections
          </button>
          <label className="service-file">
            Importer des corrections
            <input
              type="file"
              accept="application/json,.json"
              onChange={async (e) => {
                const file = e.target.files[0];
                e.target.value = "";
                if (!file) return;
                try {
                  if (file.size > 500000)
                    throw new Error("Fichier trop volumineux.");
                  const data = await api(
                    "learning/import",
                    JSON.parse(await file.text()),
                  );
                  setMessage(
                    `${data.count} phrases mémorisées. Les corrections restent à valider.`,
                  );
                } catch (error) {
                  setMessage(error.message);
                }
              }}
            />
          </label>
          <button
            onClick={async () => {
              try {
                await api("learning/reset", {});
                setMessage(
                  "Les corrections mémorisées ont été réinitialisées.",
                );
              } catch (e) {
                setMessage(e.message);
              }
            }}
          >
            Réinitialiser les corrections
          </button>
          <p>
            Les temps du moteur excluent votre décision et le rendu physique.
            Pour un audio personnel non annoté, le bilan ne connaît pas les
            passages manqués.
          </p>
        </section>
      </div>
    </>
  );
}
