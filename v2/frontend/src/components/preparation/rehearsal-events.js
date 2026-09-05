export function rehearsalResults(result) {
  if (!/[\p{L}\p{N}]/u.test(result.text || '')) return []
  const primary = result.candidate
  if (!primary) return [result]
  const { references_multiples: additional = [], ...candidate } = primary
  return [candidate, ...additional].map((item) => ({
    ...result,
    candidate: item,
  }))
}
