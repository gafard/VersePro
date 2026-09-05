const meterShapes = {
  short: [7, 10, 15, 9, 18, 12, 22, 14, 19, 11, 25, 16, 20, 13, 24, 10, 17, 8, 14, 7, 12, 9, 6, 8, 5, 7, 4, 6],
  wide: [8, 11, 15, 9, 18, 12, 22, 14, 19, 11, 25, 16, 20, 13, 28, 17, 23, 12, 31, 18, 26, 14, 22, 16, 27, 13, 20, 11, 24, 16, 30, 18, 25, 15, 22, 11, 19, 13, 26, 17, 23, 12, 20, 10, 16, 9, 14, 8]
}

const RELEASE_PAGE = 'https://github.com/gafard/VersePro/releases/latest'
const RELEASE_API = 'https://api.github.com/repos/gafard/VersePro/releases/latest'
const FALLBACK_RELEASE = {
  version: 'v2.1.8',
  windows: 'https://github.com/gafard/VersePro/releases/download/v2.1.8/VersePro_2.1.8_x64-setup.exe',
  macos: 'https://github.com/gafard/VersePro/releases/download/v2.1.8/VersePro_2.1.8_aarch64.dmg'
}

const detectPlatform = () => {
  const platform = `${navigator.userAgentData?.platform || navigator.platform || ''} ${navigator.userAgent || ''}`.toLowerCase()
  if (/android|iphone|ipad|ipod/.test(platform) || (platform.includes('mac') && navigator.maxTouchPoints > 1)) return 'mobile'
  if (platform.includes('win')) return 'windows'
  if (platform.includes('mac')) return 'macos'
  return 'other'
}

const findReleaseAssets = (release) => {
  const assets = Array.isArray(release?.assets) ? release.assets : []
  const windows = assets.find((asset) => /_x64-setup\.exe$/i.test(asset.name))?.browser_download_url
  const macos = assets.find((asset) => /_aarch64\.dmg$/i.test(asset.name))?.browser_download_url
  return {
    version: release?.tag_name || FALLBACK_RELEASE.version,
    windows: windows || FALLBACK_RELEASE.windows,
    macos: macos || FALLBACK_RELEASE.macos
  }
}

const applyRelease = (release) => {
  const platform = detectPlatform()
  const platformName = platform === 'windows' ? 'Windows · installateur x64' : platform === 'macos' ? 'Mac · version pour puces Apple uniquement' : 'Choisissez le système de votre ordinateur'
  const directUrl = platform === 'windows' ? release.windows : '#telecharger'

  document.querySelectorAll('[data-platform-download="windows"]').forEach((link) => {
    link.href = release.windows
    link.rel = 'noreferrer'
    link.classList.toggle('is-detected', platform === 'windows')
  })
  document.querySelectorAll('[data-platform-download="macos"]').forEach((link) => {
    link.href = release.macos
    link.rel = 'noreferrer'
    link.classList.toggle('is-detected', platform === 'macos')
  })
  document.querySelectorAll('[data-auto-download]').forEach((link) => {
    link.href = directUrl
    link.rel = 'noreferrer'
    const label = link.querySelector('[data-download-label]')
    if (!label) return
    if (platform !== 'windows') label.textContent = platform === 'mobile' ? 'pour mon ordinateur' : 'choisir ma version'
    else if (link.classList.contains('nav-download')) label.textContent = platform === 'windows' ? 'Windows' : 'macOS'
    else label.textContent = `télécharger pour ${platform === 'windows' ? 'Windows' : 'macOS'}`
  })

  const detection = document.querySelector('[data-system-detection]')
  if (detection) detection.textContent = platformName

  document.querySelectorAll('[data-release-version]').forEach((element) => {
    element.textContent = `${release.version} · gratuit`
  })
}

applyRelease(FALLBACK_RELEASE)

fetch(RELEASE_API, { headers: { Accept: 'application/vnd.github+json' } })
  .then((response) => response.ok ? response.json() : Promise.reject(new Error('release unavailable')))
  .then((release) => applyRelease(findReleaseAssets(release)))
  .catch(() => {})

document.querySelectorAll('.wave').forEach((wave) => {
  const shape = wave.classList.contains('wave-wide') ? meterShapes.wide : meterShapes.short
  const fragment = document.createDocumentFragment()

  shape.forEach((height, index) => {
    const bar = document.createElement('span')
    bar.style.setProperty('--bar-height', `${height}px`)
    bar.style.setProperty('--bar-delay', `${index * -47}ms`)
    fragment.appendChild(bar)
  })

  wave.replaceChildren(fragment)
})

const menuButton = document.querySelector('.menu-toggle')
const menu = document.querySelector('.nav-links')

menuButton?.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true'
  menuButton.setAttribute('aria-expanded', String(!isOpen))
  menu.classList.toggle('is-open', !isOpen)
})

menu?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    menuButton?.setAttribute('aria-expanded', 'false')
    menu.classList.remove('is-open')
  })
})

const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return
    entry.target.classList.add('is-visible')
    revealObserver.unobserve(entry.target)
  })
}, { threshold: 0.12 })

document.querySelectorAll('.reveal').forEach((element, index) => {
  element.style.transitionDelay = `${Math.min(index % 4, 3) * 60}ms`
  revealObserver.observe(element)
})

const demoCases = {
  explicit: { transcript: '« Ouvrons Jean, chapitre trois, verset seize. »', reference: 'Jean 3:16', reason: 'référence entendue', text: 'Car Dieu a tant aimé le monde qu’il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu’il ait la vie éternelle.' },
  paraphrase: { transcript: '« Sa parole nous éclaire, comme une lampe sur le chemin. »', reference: 'Psaume 119:105', reason: 'rapprochement à vérifier', text: 'Ta parole est une lampe à mes pieds, et une lumière sur mon sentier.' },
  negative: { transcript: '« Le rendez-vous de l’équipe est à dix-huit heures. »', reference: 'Aucun verset proposé', reason: 'une annonce ordinaire', text: '' }
}
let demoCase = 'explicit'
const demoButton = document.querySelector('[data-demo-validate]')
const setDemoText = (selector, text) => { const node = document.querySelector(selector); if (node) node.textContent = text }
function resetDemoScreen() {
  setDemoText('[data-demo-output-text]', 'Le passage s’affichera après votre validation.')
  setDemoText('[data-demo-output-ref]', 'ÉCRAN DE DÉMONSTRATION')
  setDemoText('[data-demo-status]', demoCases[demoCase].text ? 'à vous de valider' : 'aucune projection à faire')
  demoButton?.classList.remove('is-valid')
}
document.querySelectorAll('[data-demo-case]').forEach(button => button.addEventListener('click', () => {
  demoCase = button.dataset.demoCase
  const example = demoCases[demoCase]
  document.querySelectorAll('[data-demo-case]').forEach(b => b.setAttribute('aria-pressed', String(b === button)))
  setDemoText('[data-demo-transcript]', example.transcript)
  setDemoText('[data-demo-reference]', example.reference)
  setDemoText('[data-demo-reason]', example.reason)
  if (demoButton) demoButton.disabled = !example.text
  resetDemoScreen()
}))
demoButton?.addEventListener('click', () => {
  const example = demoCases[demoCase]
  if (!example.text) return
  setDemoText('[data-demo-output-text]', example.text)
  setDemoText('[data-demo-output-ref]', example.reference + ' · LSG')
  setDemoText('[data-demo-status]', 'passage affiché dans la simulation')
  demoButton.classList.add('is-valid')
})
document.querySelector('[data-demo-reset]')?.addEventListener('click', resetDemoScreen)

const DIRECT_MONEYFUSION_URL = 'https://my.moneyfusion.net/6a8a6993ff0cbef4d3e52f9b'

document.querySelectorAll('[data-open-donation]').forEach((link) => {
  link.href = DIRECT_MONEYFUSION_URL
  link.target = '_blank'
  link.rel = 'noreferrer'
})
