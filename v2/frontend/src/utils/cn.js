/**
 * Helper d'assemblage conditionnel de classes CSS / Tailwind.
 * Permet de concaténer proprement des chaînes de classes en éliminant les valeurs falsy.
 */
export function cn(...inputs) {
  return inputs.flat().filter(Boolean).join(' ')
}
