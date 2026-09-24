// L'avis de l'assistant arrive APRÈS la liste locale de la barre de recherche.
//
// /api/v1/bible/search répond tout de suite, sans IA. /api/v1/bible/search/ia
// rend ensuite la même liste, complétée par la proposition vérifiée de l'IA
// placée en tête. Mesuré sur 45 descriptions : top 3 de 80–93 % en local
// seul, 100 % avec l'IA, qui arrive environ 1,2 s plus tard (p50).
//
// Remplacer la liste pendant que le régisseur navigue au clavier ne doit pas
// déplacer la sélection sous ses doigts : l'élément actif reste actif.

export function fusionnerAvisIA(anciens, nouveaux, indexActif) {
  const liste = Array.isArray(nouveaux) ? nouveaux : []
  const actif = anciens?.[indexActif]?.reference
  if (!actif || indexActif === 0) return { results: liste, activeIndex: 0 }
  const retrouve = liste.findIndex((r) => r.reference === actif)
  return { results: liste, activeIndex: retrouve >= 0 ? retrouve : 0 }
}

// Une description vaut la peine d'interroger l'IA ; une référence ou un mot seul, non.
export function meriteAvisIA(requete) {
  const texte = String(requete || '').trim()
  if (texte.split(/\s+/).length < 2) return false
  // « Jean 3:16 », « 1 Co 13 4 », « Ps 23 » : une référence n'a pas besoin d'IA.
  return !/^\s*(?:[1-3]\s*)?[A-Za-zÀ-ÿ]+\.?\s+\d+(?:\s*[:.,\s]\s*\d+)?(?:\s*[-–]\s*\d+)?\s*$/.test(texte)
}

export function libelleIA(resultat) {
  if (resultat?.source === 'ai') return 'Suggestion IA — à relire'
  if (resultat?.ia_confirme) return 'Confirmé par l’IA'
  return ''
}
