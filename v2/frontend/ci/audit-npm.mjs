// Audit npm de la CI : refuse toute vulnérabilité « high » ou « critical »,
// sauf les exceptions listées dans audit-exceptions.json — chacune justifiée
// et DATÉE. Une exception échue fait échouer la CI : elle se réexamine,
// elle ne s'oublie pas.
//
// Pourquoi pas `npm audit --audit-level=high` seul : le 18 septembre 2026,
// GHSA-vfj7-8cjw-p6xm a touché toutes les versions de `braces` sans qu'aucune
// version corrigée n'existe. `main` passait au rouge sans rien qu'on puisse
// mettre à jour, et la seule « correction » proposée était un saut forcé de
// Tailwind 3 à 4. Désactiver l'audit aurait aussi masqué les suivantes.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const BLOQUANTES = new Set(['high', 'critical'])
const exceptions = JSON.parse(readFileSync(new URL('../audit-exceptions.json', import.meta.url), 'utf8'))
const aujourdhui = new Date().toISOString().slice(0, 10)

let brut
try {
  brut = execFileSync('npm', ['audit', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
} catch (erreur) {
  brut = erreur.stdout // npm audit sort en erreur dès qu'il trouve quelque chose
}
const rapport = JSON.parse(brut)
if (rapport.error) {
  console.error(`npm audit n'a pas pu s'exécuter : ${rapport.error.summary || rapport.error.code}`)
  process.exit(1)
}

// Les avis eux-mêmes (pas les paquets qui en héritent par dépendance).
const avis = new Map()
for (const vulnerabilite of Object.values(rapport.vulnerabilities || {})) {
  for (const source of vulnerabilite.via) {
    if (typeof source === 'object' && BLOQUANTES.has(source.severity)) {
      avis.set(source.url.split('/').pop(), source)
    }
  }
}

let echec = false
for (const [id, source] of avis) {
  const exception = exceptions.find((e) => e.avis === id)
  if (!exception) {
    console.error(`✗ ${source.severity} ${source.name} ${source.range} — ${id} : ${source.title}`)
    echec = true
  } else if (exception.revoir_avant < aujourdhui) {
    console.error(`✗ exception échue le ${exception.revoir_avant} pour ${id} (${source.name}) : à réexaminer`)
    echec = true
  } else {
    console.log(`⚠ ${id} (${source.name}) toléré jusqu'au ${exception.revoir_avant} : ${exception.raison}`)
  }
}
for (const exception of exceptions) {
  if (!avis.has(exception.avis)) console.log(`ℹ exception ${exception.avis} devenue inutile : à retirer`)
}
if (echec) process.exit(1)
console.log(`✓ aucune vulnérabilité high/critical hors exceptions (${avis.size} avis examinés)`)
