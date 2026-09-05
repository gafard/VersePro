# Mises à jour automatiques de VersePro

VersePro vérifie silencieusement la dernière GitHub Release au démarrage. Si
une version plus récente existe, l'opérateur peut la télécharger, la vérifier
et l'installer depuis l'application. L'installation est refusée tant que le
micro ou la sortie à l'antenne est actif.

L'Updater est présent dans la branche 2.1 et dans la version courante 2.1.8.
Une installation antérieure à son introduction doit recevoir une version 2.1
une dernière fois par installation manuelle; les versions suivantes peuvent
ensuite se mettre à jour depuis VersePro.

## Clé de signature Updater

La paire de clés de production a été créée localement dans :

```text
.secrets/versepro-updater.key
.secrets/versepro-updater.key.pub
```

Ce dossier est ignoré par Git. La clé privée ne doit jamais être ajoutée au
dépôt. Conservez-en une sauvegarde chiffrée : sa perte empêcherait toute mise à
jour des installations existantes.

Après authentification avec GitHub CLI, enregistrer la clé privée dans le dépôt :

```bash
gh auth login
gh secret set TAURI_SIGNING_PRIVATE_KEY < .secrets/versepro-updater.key
```

La clé n'a pas de mot de passe afin de fonctionner dans GitHub Actions sans
secret secondaire. GitHub chiffre le secret au repos et ne permet pas de le
relire après enregistrement.

## Signatures des systèmes

La signature Updater protège l'intégrité de la mise à jour. Elle ne remplace
pas les certificats de distribution du système :

- macOS : `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` ;
- Windows : `WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD`.

La clé Updater est obligatoire pour une release par tag. Les certificats Apple
et Windows sont vivement recommandés, mais leur absence ne bloque plus la
publication : macOS pourra afficher Gatekeeper et Windows SmartScreen jusqu'à
leur ajout. Un lancement manuel du workflow peut aussi produire des
installateurs de test sans clé Updater.

## Publier une version

1. Mettre la même version dans `tauri.conf.json`, `Cargo.toml`, `package.json`
   et le backend.
2. Pousser le commit sur `main` et attendre la réussite de la CI.
3. Créer puis pousser le tag correspondant, par exemple `v2.1.8`.
4. Le workflow construit macOS Apple Silicon et Windows x64, publie les
   installateurs et génère `latest.json` dans la GitHub Release.

Le tag et la version de l'application doivent être identiques. Le workflow
vérifie cette condition avant toute construction.

Le dépôt de releases — ou au minimum l'hébergement de `latest.json` et des
artefacts — doit être accessible publiquement. Une application installée ne
possède pas le jeton GitHub du développeur et ne peut pas télécharger les assets
d'un dépôt privé.
