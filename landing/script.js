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
  const platformName = platform === 'windows' ? 'Windows x64' : platform === 'macos' ? 'macOS Apple Silicon' : 'système non pris en charge automatiquement'
  const directUrl = platform === 'other' ? RELEASE_PAGE : release[platform]

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
    if (platform === 'other') label.textContent = 'voir les téléchargements'
    else if (link.classList.contains('nav-download')) label.textContent = platform === 'windows' ? 'Windows' : 'macOS'
    else label.textContent = `télécharger pour ${platform === 'windows' ? 'Windows' : 'macOS'}`
  })

  const detection = document.querySelector('[data-system-detection]')
  if (detection) detection.textContent = platform === 'other'
    ? 'Linux ou système inconnu · consultez les fichiers disponibles'
    : `${platformName} détecté · téléchargement direct prêt`

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

const demoButton = document.querySelector('[data-demo-validate]')
demoButton?.addEventListener('click', () => {
  demoButton.classList.add('is-valid')
  demoButton.textContent = 'à l’antenne ✓'
})

const donationEndpoint = '/api/donations'
const donationLink = document.querySelector('[data-open-donation]')
const donationDialog = document.querySelector('#donation-dialog')
const donationForm = document.querySelector('[data-donation-form]')
const donationStatus = document.querySelector('[data-donation-status]')
const donationSubmit = donationForm?.querySelector('[type="submit"]')

const setDonationStatus = (message = '', isError = false) => {
  if (!donationStatus) return
  donationStatus.textContent = message
  donationStatus.classList.toggle('is-error', isError)
}

const enableMoneyFusion = () => {
  if (!donationLink || !donationDialog) return
  donationLink.href = '#soutenir'
  donationLink.addEventListener('click', (event) => {
    event.preventDefault()
    setDonationStatus()
    donationDialog.showModal()
  })
}

fetch(donationEndpoint, { headers: { Accept: 'application/json' } })
  .then((response) => response.ok ? response.json() : Promise.reject(new Error('donation unavailable')))
  .then((status) => {
    if (status?.enabled === true) enableMoneyFusion()
  })
  .catch(() => {})

document.querySelector('[data-close-donation]')?.addEventListener('click', () => donationDialog?.close())
donationDialog?.addEventListener('click', (event) => {
  if (event.target === donationDialog) donationDialog.close()
})

document.querySelectorAll('[data-amount]').forEach((button) => {
  button.addEventListener('click', () => {
    const amount = donationForm?.elements.namedItem('amount')
    if (amount) amount.value = button.dataset.amount
    document.querySelectorAll('[data-amount]').forEach((item) => item.classList.toggle('is-selected', item === button))
  })
})

const DIRECT_MONEYFUSION_URL = 'https://my.moneyfusion.net/6a8a6993ff0cbef4d3e52f9b'

donationForm?.addEventListener('submit', async (event) => {
  event.preventDefault()
  if (!donationForm.reportValidity()) return

  donationSubmit.disabled = true
  setDonationStatus('Redirection vers la page de paiement sécurisée…')

  try {
    const formData = new FormData(donationForm)
    const payload = {
      amount: Number(formData.get('amount')),
      name: String(formData.get('name') || '').trim(),
      phone: String(formData.get('phone') || '').trim()
    }

    const response = await fetch(donationEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload)
    })
    
    if (response.ok) {
      const result = await response.json()
      if (result?.statut === true && result?.url) {
        window.location.assign(result.url)
        return
      }
    }
  } catch (error) {
    // Si l'API serveur Vercel n'est pas configurée, on redirige directement vers le lien public MoneyFusion
  }

  window.location.assign(DIRECT_MONEYFUSION_URL)
})
