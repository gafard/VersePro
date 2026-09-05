// Dix versets autour de celui qui est à l'antenne.
//
// Cinq avant, cinq après. Mais un prédicateur qui ouvre au verset 1 n'a rien
// derrière lui : la fenêtre se décale pour montrer dix versets en avant, et
// symétriquement dix en arrière sur le dernier verset du chapitre. On garde
// toujours dix propositions, jamais cinq boutons morts.
//
// Le calcul vit ici, hors du composant, pour être vérifiable : c'est une
// arithmétique de bornes, et les bornes sont précisément ce qui se trompe.
export const PORTEE_VOISINS = 5

export function versetsVoisins(courant, total, portee = PORTEE_VOISINS) {
  if (!Number.isInteger(courant) || !Number.isInteger(total)) return []
  if (total < 2 || courant < 1 || courant > total) return []

  let debut = courant - portee
  let fin = courant + portee
  if (debut < 1) { fin += 1 - debut; debut = 1 }
  if (fin > total) { debut -= fin - total; fin = total }
  if (debut < 1) debut = 1

  const numeros = []
  for (let v = debut; v <= fin; v += 1) if (v !== courant) numeros.push(v)
  return numeros
}
