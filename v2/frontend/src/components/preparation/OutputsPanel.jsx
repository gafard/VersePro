import ScreenCheck from "./ScreenCheck.jsx";
import React, { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, saveFile } from "./api.js";
import { BACKEND_BASE, openExternal } from "../../env.js";

export default function OutputsPanel() {
  const [delivery, setDelivery] = useState(null),
    [sharing, setSharing] = useState(null),
    [pair, setPair] = useState(null),
    [qr, setQr] = useState(""),
    [role, setRole] = useState("viewer"),
    [view, setView] = useState("follow"),
    [ip, setIp] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let mounted = true,
      timer;
    async function poll() {
      try {
        const [d, s] = await Promise.all([api("delivery"), api("companion")]);
        if (mounted) {
          setDelivery(d);
          setSharing(s);
        }
      } catch (e) {
        if (mounted) setMessage(e.message);
      } finally {
        if (mounted) timer = setTimeout(poll, 3000);
      }
    }
    poll();
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, []);
  const url = pair
    ? `http://${ip || pair.ips[0]}:${pair.port}/?view=${view}#token=${pair.token}`
    : "";
  useEffect(() => {
    let active = true;
    if (url)
      QRCode.toDataURL(url, { width: 240, margin: 2 })
        .then((data) => {
          if (active) setQr(data);
        })
        .catch(() =>
          setMessage("Le QR code n’a pas pu être créé. Copiez le lien."),
        );
    else setQr("");
    return () => {
      active = false;
    };
  }, [url]);
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
  return (
    <div className="service-layout">
      <section className="service-panel">
        <h2>Ce que reçoivent les écrans</h2>
        <p>
          {delivery
            ? `${delivery.connected} écran(s) connecté(s) · ${delivery.rendered} rendu(s) confirmé(s)`
            : "Lecture des sorties…"}
        </p>
        <div className="service-actions">
          <button onClick={() => openExternal(`${BACKEND_BASE}/output`)}>
            Ouvrir l’écran salle
          </button>
          <button onClick={() => openExternal(`${BACKEND_BASE}/obs`)}>
            Ouvrir la source OBS
          </button>
          <button onClick={() => openExternal(`${BACKEND_BASE}/stage`)}>
            Ouvrir le retour scène
          </button>
        </div>
        <ul className="delivery-list">
          {delivery?.clients.map((c) => (
            <li key={c.client_id}>
              <strong>
                {c.surface} · {c.client_id}
              </strong>
              <span className={c.status === "rendered" ? "service-ok" : ""}>
                {c.status === "rendered"
                  ? "Rendu confirmé"
                  : "Envoyé · rendu non confirmé"}
              </span>
            </li>
          ))}
        </ul>
        {delivery?.connected === 0 && (
          <p className="service-empty">
            Aucun écran connecté. Ouvrez une sortie pour vérifier le rendu.
          </p>
        )}
        <p>
          Un rendu confirme la réception par la page. Vérifiez aussi que le
          projecteur est allumé et que la source OBS est visible dans votre
          programme.
        </p>
        <ScreenCheck />
        <hr />
        <button
          onClick={() =>
            run(async () =>
              saveFile("diagnostic-versepro.json", await api("diagnostic")),
            )
          }
          disabled={busy}
        >
          Exporter un diagnostic
        </button>
        <small>
          Version, moteurs et états techniques uniquement. Aucun audio,
          transcript ou secret.
        </small>
      </section>
      <section className="service-panel">
        <h2>Le compagnon de la salle</h2>
        <p>
          Partagez les passages sur le même réseau Wi-Fi. Chaque partage dure au
          plus huit heures.
        </p>
        <label>
          Accès accordé
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="viewer">Lecture seulement</option>
            <option value="operator">Lecture et télécommande</option>
          </select>
        </label>
        <label>
          Affichage
          <select value={view} onChange={(e) => setView(e.target.value)}>
            <option value="follow">Assemblée</option>
            <option value="stage">Retour prédicateur</option>
          </select>
        </label>
        <div className="service-actions">
          <button
            className="primary"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const p = await api("companion/start", { role });
                setPair(p);
                setIp(p.ips[0]);
                setSharing(p);
              })
            }
          >
            {sharing?.active ? "Renouveler le partage" : "Activer le partage"}
          </button>
          <button
            disabled={busy || !sharing?.active}
            onClick={() =>
              run(async () => {
                setSharing(await api("companion/stop", {}));
                setPair(null);
              })
            }
          >
            Arrêter
          </button>
        </div>
        {pair && sharing?.active && (
          <>
            <label>
              Réseau
              <select value={ip} onChange={(e) => setIp(e.target.value)}>
                {pair.ips.map((i) => (
                  <option key={i}>{i}</option>
                ))}
              </select>
            </label>
            {qr && (
              <img
                className="companion-qr"
                src={qr}
                alt="QR code d’accès temporaire aux passages"
              />
            )}
            <p>
              {pair.role === "operator"
                ? "Ce QR permet de projeter et d’effacer les passages."
                : "Ce QR permet uniquement de lire les passages."}
            </p>
            <button
              onClick={() =>
                run(async () => {
                  await navigator.clipboard.writeText(url);
                  setMessage("Lien copié.");
                })
              }
            >
              Copier le lien
            </button>
            {ip === "127.0.0.1" && (
              <p>
                Aucun réseau local détecté. Connectez cet ordinateur au Wi-Fi de
                la salle.
              </p>
            )}
          </>
        )}
        {sharing?.active && !pair && (
          <p>
            Un partage est actif. Renouvelez-le pour obtenir un nouveau QR ; les
            anciens accès seront fermés.
          </p>
        )}
        <p role="status">{message}</p>
      </section>
    </div>
  );
}
