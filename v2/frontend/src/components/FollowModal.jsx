import React, { useEffect, useRef } from "react";
import OutputsPanel from "./preparation/OutputsPanel.jsx";
import "./preparation/service-desk.css";
export default function FollowModal({ isOpen, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    if (isOpen && !dialog.current.open) dialog.current.showModal();
    if (!isOpen && dialog.current.open) dialog.current.close();
  }, [isOpen]);
  return (
    <dialog
      ref={dialog}
      className="service-network-dialog service-desk"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label="Écrans et partage local"
    >
      <div className="service-intro">
        <h2>Écrans et partage local</h2>
        <button onClick={onClose}>Fermer</button>
      </div>
      {isOpen && <OutputsPanel />}
    </dialog>
  );
}
