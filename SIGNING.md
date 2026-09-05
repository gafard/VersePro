# Signer VersePro au nom de Selah Studios

Le câblage Tauri et GitHub Actions est prêt. Une release par tag exige la clé de
signature de l'Updater; sans elle, aucun artefact auto-installable n'est publié.
Les certificats Apple et Windows restent vivement recommandés mais ne bloquent
plus techniquement la publication : en leur absence, le workflow émet un
avertissement et les systèmes peuvent afficher Gatekeeper ou SmartScreen. Un
workflow manuel peut produire un paquet de test explicitement non signé.

## macOS — Apple Developer (99 $/an)

1. **Inscrire Selah Studios** au programme Apple Developer :
   <https://developer.apple.com/programs/enroll/> (compte « Organization » ;
   demande un numéro D-U-N-S, gratuit, délai de quelques jours).
2. Dans l'app **Keychain Access** du Mac : Certificate Assistant → *Request a
   Certificate From a Certificate Authority* (fichier `.certSigningRequest`).
3. Sur <https://developer.apple.com/account/resources/certificates> : créer un
   certificat **Developer ID Application** avec ce fichier, le télécharger,
   double-cliquer pour l'installer dans le trousseau.
4. Exporter le certificat + clé privée en **`.p12`** (clic droit dans Keychain
   → Exporter, choisir un mot de passe).
5. Créer un **mot de passe d'application** pour la notarisation :
   <https://account.apple.com> → Sign-In and Security → App-Specific Passwords.
6. Renseigner les secrets GitHub (dépôt → Settings → Secrets → Actions) :

   | Secret | Valeur |
   |---|---|
   | `APPLE_CERTIFICATE` | le `.p12` encodé : `base64 -i selah.p12 \| pbcopy` |
   | `APPLE_CERTIFICATE_PASSWORD` | mot de passe choisi à l'export |
   | `APPLE_SIGNING_IDENTITY` | `Developer ID Application: Selah Studios (TEAMID)` |
   | `APPLE_ID` | l'identifiant Apple du compte |
   | `APPLE_PASSWORD` | le mot de passe d'application (étape 5) |
   | `APPLE_TEAM_ID` | le Team ID (visible sur developer.apple.com/account) |

Le bundler Tauri détecte ces variables et signe + notarise sans autre réglage.
Pour signer aussi les builds **locaux** (`build-macos.sh`), exporter les mêmes
variables dans le shell avant de lancer le script.

## Windows — certificat de signature de code (~200–400 €/an)

1. Acheter un certificat **OV Code Signing** au nom de Selah Studios chez une
   autorité (Certum, Sectigo, GlobalSign…). Vérification d'identité de
   l'entreprise requise (documents officiels, quelques jours).
   Note : depuis 2023 les clés doivent vivre sur support matériel (token USB ou
   HSM cloud). Pour la CI, choisir une offre **« cloud signing »** ou exporter
   un `.pfx` si l'autorité le permet encore.
2. Si vous avez un `.pfx` : renseigner les secrets GitHub :

   | Secret | Valeur |
   |---|---|
   | `WINDOWS_CERTIFICATE` | le `.pfx` encodé : `base64 -i selah.pfx \| pbcopy` |
   | `WINDOWS_CERTIFICATE_PASSWORD` | mot de passe du `.pfx` |

   Le workflow importe le certificat sur le runner, renseigne son empreinte
   dans la config Tauri et horodate chez DigiCert.
3. Offre cloud (Azure Trusted Signing, Certum SimplySign…) : me redemander le
   câblage, il diffère selon le fournisseur.

## Ce qui est déjà fait dans le dépôt

- Branding **Selah Studios** : copyright, éditeur, descriptions (tauri.conf,
  Cargo.toml).
- `release.yml` : signature macOS native Tauri via secrets ; import du
  certificat Windows + empreinte + horodatage via secrets ; avertissements si
  un certificat OS manque ; blocage strict si la clé Updater manque lors d'une
  publication par tag.
- Updater Tauri : clé publique embarquée, manifeste `latest.json`, artefacts
  signés et installation interdite pendant le direct.
