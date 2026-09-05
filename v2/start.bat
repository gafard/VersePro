@echo off
setlocal EnableDelayedExpansion

title VersePro v2 - Lanceur

set DIR=%~dp0
set BACKEND_PORT=8001
set FRONTEND_PORT=3001
if not "%VERSEPRO_BACKEND_PORT%"=="" set BACKEND_PORT=%VERSEPRO_BACKEND_PORT%
if not "%VERSEPRO_FRONTEND_PORT%"=="" set FRONTEND_PORT=%VERSEPRO_FRONTEND_PORT%

echo ====================================================
echo     🔵 PREPARATION DE VOTRE CONSOLE VERSEPRO V2
echo ====================================================
echo   Veuillez patienter pendant le démarrage automatique...
echo.

cd /d "%DIR%" || goto :error

if not exist "%DIR%logs" mkdir "%DIR%logs"
echo --- Lancement Windows du %date% %time% --- > "%DIR%logs\install.log"

rem Étape 1 : Analyse Système
echo [1/3] Analyse des composants systeme...
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERREUR] Python 3 n'est pas detecte. Veuillez l'installer.
    goto :error
  )
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] Node.js n'est pas detecte. Veuillez l'installer.
  goto :error
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] npm (Node Package Manager) n'est pas detecte.
  goto :error
)
echo      👉 Composants systeme verifies avec succes.

rem Étape 2 : Préparation du backend
echo [2/3] Preparation du moteur VersePro... (Veuillez patienter)
cd /d "%DIR%backend" || goto :error

if not exist "venv\Scripts\python.exe" (
  python -m venv venv >> "%DIR%logs\install.log" 2>&1
  if errorlevel 1 py -3 -m venv venv >> "%DIR%logs\install.log" 2>&1
  if errorlevel 1 goto :error
)

if not exist "venv\.versepro_deps_installed" (
  venv\Scripts\python.exe -m pip install --upgrade pip >> "%DIR%logs\install.log" 2>&1
  venv\Scripts\python.exe -m pip install -r requirements.txt >> "%DIR%logs\install.log" 2>&1
  if errorlevel 1 goto :error
  type nul > "venv\.versepro_deps_installed"
)

curl -fsS http://127.0.0.1:%BACKEND_PORT%/ 2>nul | findstr /C:"VersePro v2" >nul
if errorlevel 1 (
  netstat -ano | findstr :%BACKEND_PORT% | findstr LISTENING >nul
  if not errorlevel 1 (
    echo [ERREUR] Le port backend %BACKEND_PORT% est occupe.
    goto :error
  )
  start "VersePro Backend" /min cmd /c "venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% > \"%DIR%logs\backend.log\" 2>&1"
)
echo      👉 Moteur demarre avec succes.

rem Étape 3 : Préparation du frontend
echo [3/3] Lancement de l'interface visuelle...
cd /d "%DIR%frontend" || goto :error

if not exist "node_modules" (
  npm install >> "%DIR%logs\install.log" 2>&1
  if errorlevel 1 goto :error
)

:find_frontend_port
netstat -ano | findstr :!FRONTEND_PORT! | findstr LISTENING >nul
if not errorlevel 1 (
  set /a FRONTEND_PORT+=1
  if !FRONTEND_PORT! GTR 3010 (
    echo [ERREUR] Aucun port frontend libre entre 3001 et 3010.
    goto :error
  )
  goto :find_frontend_port
)

start "VersePro Frontend" /min cmd /c "set VITE_BACKEND_PORT=%BACKEND_PORT%&& npm run dev -- --host 127.0.0.1 --port !FRONTEND_PORT! > \"%DIR%logs\frontend.log\" 2>&1"

timeout /t 4 >nul
start http://127.0.0.1:!FRONTEND_PORT!

echo ====================================================
echo   🟢 VERSEPRO EST PRET ET EN COURS D'EXECUTION !
echo   Adresse de la console : http://127.0.0.1:!FRONTEND_PORT!
echo   Logs d'execution      : %DIR%logs
echo   Ne fermez pas cette fenetre pour maintenir l'application.
echo ====================================================
pause
exit /b 0

:error
echo.
echo 🛑 Oups ! Nous avons rencontre une difficulte lors du lancement.
echo Pas de panique ! Voici comment debloquer la situation :
echo  1. Verifiez que votre ordinateur est connecte a Internet.
echo  2. Fermez cette fenetre et relancez VersePro.
echo  3. Si le probleme persiste, le detail de l'erreur se trouve dans :
echo     %DIR%logs\install.log
echo     Vous pouvez aussi consulter le guide 'Depannage d'urgence' dans le README.md.
echo.
pause
exit /b 1
