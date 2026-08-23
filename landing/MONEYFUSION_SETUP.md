# Configuration MoneyFusion pour VersePro

## Informations à saisir dans le tableau de bord

| Champ MoneyFusion | Valeur VersePro |
| --- | --- |
| Type d'application | `Application` |
| Nom de l'application | `VersePro` |
| Description | `VersePro est une application de bureau gratuite conçue pour détecter les références bibliques pendant les prédications et préparer leur projection en direct sur macOS et Windows.` |
| Logo | `assets/versepro-moneyfusion-logo.png` |
| Nom du site/App | `VersePro` |
| Adresse site/application | `https://versepro-green.vercel.app` |
| URL de redirection | `https://versepro-green.vercel.app/don/merci.html` |
| Adresse IP autorisée | Une IP sortante fixe du serveur qui exécute `/api/donations` |

Ne renseignez jamais `127.0.0.1`, `192.168.x.x`, l'IP du Mac de régie ou les
adresses IP des donateurs. MoneyFusion doit recevoir l'IP publique stable de
la fonction serveur qui crée le paiement.

## Variables serveur

Configurez ces variables dans **Vercel → Project Settings → Environment
Variables**. Ne les écrivez pas dans `script.js`, `index.html` ou
`vercel.json`.

```text
MONEYFUSION_API_URL=https://URL-UNIQUE-GENEREE-PAR-MONEYFUSION
VERSEPRO_SITE_URL=https://versepro-green.vercel.app
```

La variable suivante est facultative et ne doit être renseignée que lorsqu'un
vrai endpoint de webhook a été déployé séparément :

```text
MONEYFUSION_WEBHOOK_URL=https://VOTRE-RELAIS-IP-FIXE/webhook/moneyfusion
```

Le bouton public garde son lien de contact tant que la fonction Vercel ne confirme
pas que les deux variables obligatoires sont configurées. Dès qu'elles le sont,
il ouvre automatiquement le formulaire MoneyFusion.

## Point important : IP sortante Vercel

Le plan Vercel Hobby ne garantit pas une IP sortante unique pour les fonctions.
Or MoneyFusion demande une IP autorisée. La landing et les téléchargements
peuvent être publiés immédiatement sur Vercel, mais le paiement ne doit être
activé qu'après l'une de ces validations :

1. MoneyFusion accepte d'autoriser les plages d'IP Vercel ;
2. le projet Vercel dispose d'une sortie réseau à IP fixe ;
3. `/api/donations` est déplacé vers un petit relais HTTPS à IP fixe.

## Vérification

1. Déployer le dossier `landing/` sur Vercel.
2. Ajouter les variables d'environnement, puis redéployer la production.
3. Ouvrir `https://versepro-green.vercel.app/api/donations` : la réponse attendue est
   `{"enabled":true}`.
4. Lancer un don de test de `200 FCFA` minimum.
5. Si MoneyFusion répond « IP non autorisée », ne pas autoriser une adresse
   temporaire : mettre en place une des trois solutions d'IP fixe ci-dessus.
