import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

export default function ScreenCheck() {
  const [scene, setScene] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const current = useRef(null);
  useEffect(
    () => () => {
      if (current.current)
        api("projection/test/finish", { scene_id: current.current }).catch(
          () => {},
        );
    },
    [],
  );
  async function start() {
    setBusy(true);
    try {
      const result = await api("projection/test", {});
      current.current = result.scene_id;
      setScene(result.scene_id);
      setMessage(
        "Regardez l’écran depuis le fond de la salle, puis confirmez sa lisibilité.",
      );
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function finish(confirmed) {
    setBusy(true);
    try {
      await api("projection/test/finish", { scene_id: scene });
      current.current = null;
      setScene(null);
      setMessage(
        confirmed
          ? "Lisibilité confirmée par l’opérateur pour cet essai."
          : "Mire terminée. Ajustez votre écran avant le culte.",
      );
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <h3>Vérifier depuis la salle</h3>
      <p>
        La mire apparaît sur les sorties navigateur. Arrêtez le micro et effacez
        le passage avant cet essai.
      </p>
      <div className="service-actions">
        {!scene ? (
          <button disabled={busy} onClick={start}>
            Afficher la mire
          </button>
        ) : (
          <>
            <button disabled={busy} onClick={() => finish(true)}>
              Je lis clairement les trois lignes
            </button>
            <button disabled={busy} onClick={() => finish(false)}>
              Terminer l’essai
            </button>
          </>
        )}
      </div>
      <p role="status">{message}</p>
    </div>
  );
}
