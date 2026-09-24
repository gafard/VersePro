// Recadrage du fond plein écran : l'écran HTML doit montrer ce que reçoit NDI.
//
// Le test exécute la VRAIE fonction placerFond d'output.html, puis compare la
// zone d'image visible aux chiffres mesurés sur le rendu NDI
// (backend/tests/test_fond_recadrage_ndi.py, même image d'essai 1600x900,
// quart gauche rouge, trame 960x540).
//
// Avant correction, l'écran posait un clip-path sur lui-même : un recadrage de
// 20 % à gauche noircissait 20 % de l'écran, là où NDI montrait l'image.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../../backend/app/templates/output.html', import.meta.url), 'utf8')
const source = html.match(/function placerFond\(\) \{[\s\S]*?\n {12}\}\n/)
assert.ok(source, 'placerFond introuvable dans output.html')

function placer(geometrie) {
  const backgroundImage = { style: {}, naturalWidth: 1600, naturalHeight: 900 }
  const backgroundLayer = { clientWidth: 960, clientHeight: 540 }
  const executer = new Function('fondGeometrie', 'backgroundImage', 'backgroundLayer', 'window',
    `${source[0]}; placerFond();`)
  executer({ fit: 'cover', x: 50, y: 50, cropT: 0, cropR: 0, cropB: 0, cropL: 0, totalScale: 1, ...geometrie },
    backgroundImage, backgroundLayer, { innerWidth: 960, innerHeight: 540 })
  return backgroundImage.style
}

// Zone visible à l'écran : boîte de l'image, moins le clip, puis le zoom.
function visible(style, g) {
  const px = (v) => parseFloat(v)
  const [left, top, w, h] = [px(style.left), px(style.top), px(style.width), px(style.height)]
  const [ox, oy] = style.transformOrigin.split(' ').map(px)
  const s = g.totalScale ?? 1
  const zx = (x) => left + ox + (x - left - ox) * s
  const zy = (y) => top + oy + (y - top - oy) * s
  const borne = (a, b, max) => [Math.round(Math.max(0, a)), Math.round(Math.min(max, b)) - 1]
  const g2 = { cropT: 0, cropR: 0, cropB: 0, cropL: 0, ...g }
  const x0 = zx(left + w * g2.cropL / 100), x1 = zx(left + w * (1 - g2.cropR / 100))
  const y0 = zy(top + h * g2.cropT / 100), y1 = zy(top + h * (1 - g2.cropB / 100))
  const rouge = [Math.max(x0, zx(left)), Math.min(x1, zx(left + w / 4))]
  return {
    x: borne(x0, x1, 960), y: borne(y0, y1, 540),
    rouge: rouge[1] > rouge[0] ? borne(rouge[0], rouge[1], 960) : null,
  }
}

test("recadrer retire une bande de l'image, pas de l'écran", () => {
  const g = { cropL: 20 }
  const style = placer(g)
  assert.equal(style.clipPath, 'inset(0% 0% 0% 20%)')
  // NDI : image sur toute la largeur, rouge de 0 à 59.
  assert.deepEqual(visible(style, g), { x: [0, 959], y: [0, 539], rouge: [0, 59] })
})

test('contain recadré : mêmes bords que NDI', () => {
  const g = { fit: 'contain', cropT: 10, cropL: 20 }
  const v = visible(placer(g), g)
  // NDI : image de 54 à 906, rouge de 54 à 106 (écart d'arrondi ≤ 1 px).
  assert.ok(Math.abs(v.x[0] - 54) <= 1 && Math.abs(v.x[1] - 906) <= 1, JSON.stringify(v))
  assert.ok(Math.abs(v.rouge[1] - 106) <= 1, JSON.stringify(v))
})

test("le zoom reste centré sur l'écran, pas sur l'image", () => {
  const g = { fit: 'contain', x: 30, cropT: 5, cropB: 20, cropL: 10, totalScale: 0.6 }
  const v = visible(placer(g), g)
  assert.deepEqual(v.x, [192, 767])
  assert.deepEqual(v.y, [135, 404])
})

test('sans recadrage, object-fit reste aux commandes', () => {
  const style = placer({ fit: 'contain', x: 30 })
  assert.equal(style.clipPath, 'none')
  assert.equal(style.objectFit, 'contain')
  assert.equal(style.objectPosition, '30% 50%')
  assert.equal(style.width, '100%')
})
