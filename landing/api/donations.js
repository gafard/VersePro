const { randomUUID } = require('node:crypto')

const json = (response, status, payload) => {
  response.statusCode = status
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.end(JSON.stringify(payload))
}

const isMoneyFusionUrl = (value) => {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && (url.hostname === 'moneyfusion.net' || url.hostname.endsWith('.moneyfusion.net'))
  } catch {
    return false
  }
}

const isPublicHttpsUrl = (value) => {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !['localhost', '127.0.0.1'].includes(url.hostname)
  } catch {
    return false
  }
}

const getSiteUrl = () => {
  const configured = String(process.env.VERSEPRO_SITE_URL || '').trim().replace(/\/$/, '')
  if (configured) return configured

  const vercelHost = process.env.VERCEL_PROJECT_PRODUCTION_URL || process.env.VERCEL_URL
  return vercelHost ? `https://${vercelHost}` : ''
}

const parseBody = (request) => {
  if (request.body && typeof request.body === 'object') return request.body
  if (typeof request.body === 'string') return JSON.parse(request.body)
  return {}
}

module.exports = async function donations(request, response) {
  const apiUrl = String(process.env.MONEYFUSION_API_URL || '').trim()
  const siteUrl = getSiteUrl()
  const enabled = isMoneyFusionUrl(apiUrl) && isPublicHttpsUrl(siteUrl)

  if (request.method === 'GET') return json(response, 200, { enabled })

  if (request.method !== 'POST') {
    response.setHeader('Allow', 'GET, POST')
    return json(response, 405, { statut: false, message: 'Méthode non autorisée.' })
  }

  if (!enabled) {
    return json(response, 503, { statut: false, message: 'Les dons en ligne ne sont pas encore configurés.' })
  }

  if (Number(request.headers['content-length'] || 0) > 4096) {
    return json(response, 413, { statut: false, message: 'Requête trop volumineuse.' })
  }

  let input
  try {
    input = parseBody(request)
  } catch {
    return json(response, 400, { statut: false, message: 'Données invalides.' })
  }

  const amount = Number(input.amount)
  const name = String(input.name || '').trim()
  const phone = String(input.phone || '').trim().replace(/[\s().-]+/g, '')

  if (!Number.isInteger(amount) || amount < 200 || amount > 5000000) {
    return json(response, 422, { statut: false, message: 'Le montant doit être compris entre 200 et 5 000 000 FCFA.' })
  }
  if (name.length < 2 || name.length > 80) {
    return json(response, 422, { statut: false, message: 'Veuillez indiquer un nom valide.' })
  }
  if (!/^\+?[0-9]{8,15}$/.test(phone)) {
    return json(response, 422, { statut: false, message: 'Veuillez indiquer un numéro Mobile Money valide.' })
  }

  const paymentData = {
    totalPrice: amount,
    article: [{ don_versepro: amount }],
    personal_Info: [{ source: 'versepro-landing', donationId: randomUUID() }],
    numeroSend: phone,
    nomclient: name,
    return_url: `${siteUrl}/don/merci.html`
  }

  const webhookUrl = String(process.env.MONEYFUSION_WEBHOOK_URL || '').trim()
  if (isPublicHttpsUrl(webhookUrl)) paymentData.webhook_url = webhookUrl

  let providerResponse
  try {
    providerResponse = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(paymentData),
      signal: AbortSignal.timeout(20000)
    })
  } catch {
    return json(response, 502, { statut: false, message: 'MoneyFusion est momentanément inaccessible.' })
  }

  let provider
  try {
    provider = await providerResponse.json()
  } catch {
    provider = null
  }

  const checkoutUrl = typeof provider?.url === 'string' ? provider.url : ''
  if (!providerResponse.ok || provider?.statut !== true || !isMoneyFusionUrl(checkoutUrl)) {
    const message = typeof provider?.message === 'string' ? provider.message : 'La demande de paiement a été refusée.'
    return json(response, 502, { statut: false, message })
  }

  return json(response, 200, {
    statut: true,
    token: typeof provider.token === 'string' ? provider.token : '',
    url: checkoutUrl
  })
}
