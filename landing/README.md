# Landing publique VersePro

La landing fonctionne sans React, Tauri ou backend VersePro. Les téléchargements
directs sont résolus depuis la dernière release GitHub. Le paiement MoneyFusion
est optionnel et passe par la fonction Vercel `/api/donations`.

## Prévisualiser localement

```bash
cd landing
python3 -m http.server 4173
```

Puis ouvrir `http://127.0.0.1:4173`. Cette adresse sert uniquement à la
prévisualisation sur la machine de développement.

## Publier sur Vercel

Le dossier `landing/` est la racine du projet Vercel. Aucun framework et aucune
commande de build ne sont nécessaires. La landing reste entièrement statique,
à l'exception de la fonction Node dans `api/donations.js`.

Production : `https://versepro-green.vercel.app`

Le bouton de soutien conserve automatiquement son lien e-mail lorsque
MoneyFusion n'est pas configuré. Pour l'activer, suivre
`MONEYFUSION_SETUP.md`. L'autorisation par IP de MoneyFusion exige une sortie
réseau fixe, qui n'est pas fournie par défaut sur le plan Vercel Hobby.

## Liens à personnaliser

- Téléchargement : `https://github.com/gafard/VersePro/releases/latest`
- Code source : `https://github.com/gafard/VersePro`
- MoneyFusion : suivre `MONEYFUSION_SETUP.md`.

Les métadonnées sociales et l'image Open Graph pointent vers le domaine de
production Vercel.
