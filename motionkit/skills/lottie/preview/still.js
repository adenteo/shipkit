// Renders one frame of a Lottie to a transparent PNG with lottie-web (SVG renderer), for places
// that show an animation's resting picture: an image costs nothing to scroll past, a Lottie view
// builds its whole layer tree each time a lazy row comes back.
//
//   node still.js <file.json> <frame> <size px> <out.png>
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const HERE = __dirname;
const CHROME = require('./chrome');
const LOTTIE = path.join(HERE, 'node_modules/lottie-web/build/player/lottie_svg.min.js');

(async () => {
  const [name, frame, size, out] = process.argv.slice(2);
  const data = JSON.parse(fs.readFileSync(path.resolve(name), 'utf8'));
  const px = +size;
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: px, height: Math.round(px * data.h / data.w), deviceScaleFactor: 1 });
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">
      <div id="b" style="width:${px}px;height:${Math.round(px * data.h / data.w)}px"></div></body></html>`);
    await page.addScriptTag({ path: LOTTIE });
    await page.evaluate((data, f) => new Promise((resolve) => {
      const a = lottie.loadAnimation({ container: document.getElementById('b'), renderer: 'svg', loop: false,
        autoplay: false, animationData: data });
      a.addEventListener('DOMLoaded', () => { a.goToAndStop(Math.min(f, data.op - 0.01), true); resolve(); });
    }), data, +frame);
    await page.screenshot({ path: out, omitBackground: true });
    console.log('wrote', out);
  } finally {
    await browser.close();
  }
})();
