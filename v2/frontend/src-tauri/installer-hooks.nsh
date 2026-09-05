; Crochets NSIS de VersePro.
;
; Le moteur de VersePro tourne dans un processus SÉPARÉ (versepro-backend.exe),
; lancé par l'application comme sidecar. L'installeur Tauri sait fermer la
; fenêtre, mais ignore l'existence de ce processus : il restait vivant pendant
; la mise à jour et gardait ses bibliothèques ouvertes.
;
; Résultat observé sur un poste d'église : « Error opening file for writing:
; ...\backend\_internal\MSVCP140_1.dll ». L'opérateur clique « Ignorer », le
; fichier est sauté, et l'installation obtenue mélange anciens et nouveaux
; fichiers — moteur qui démarre puis meurt, application « Hors ligne ».
;
; On ferme donc le moteur avant de toucher aux fichiers, à l'installation
; comme à la désinstallation. `taskkill` renvoie une erreur quand aucun
; processus ne correspond : c'est le cas normal d'une première installation,
; et il est sans conséquence ici.

!macro _VERSEPRO_ARRETER_MOTEUR
  DetailPrint "Arrêt de VersePro s'il est en cours..."
  ; L'application d'abord : elle surveille son moteur et le RELANCERAIT
  ; aussitôt si on le tuait en premier. /T emporte l'arbre de processus.
  nsExec::Exec 'taskkill /F /T /IM VersePro.exe'
  Pop $0
  ; Puis le moteur lui-même, au cas où une session précédente l'aurait laissé
  ; orphelin — c'est lui qui verrouille les DLL.
  nsExec::Exec 'taskkill /F /T /IM versepro-backend.exe'
  Pop $0
  ; Laisse à Windows le temps de relâcher les verrous de fichiers.
  Sleep 1500
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro _VERSEPRO_ARRETER_MOTEUR
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro _VERSEPRO_ARRETER_MOTEUR
!macroend
