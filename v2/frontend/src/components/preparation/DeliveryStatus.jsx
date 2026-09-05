import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import "./service-desk.css";

export default function DeliveryStatus({ onOpen }) {
  const [status, setStatus] = useState(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let active = true,
      timer;
    async function poll() {
      try {
        const result = await api("delivery");
        if (active) {
          setStatus(result);
          setUnavailable(false);
        }
      } catch {
        if (active) setUnavailable(true);
      } finally {
        if (active) timer = setTimeout(poll, 3000);
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  return (
    <div className="delivery-strip">
      <span>
        {unavailable
          ? "État des écrans indisponible"
          : !status
            ? "Lecture des écrans…"
            : status.connected === 0
              ? "Aucun écran connecté"
              : `${status.rendered}/${status.connected} écran(s) : rendu confirmé`}
      </span>
      <button className="vp-btn vp-btn--sm" onClick={onOpen}>
        Vérifier les écrans
      </button>
    </div>
  );
}
