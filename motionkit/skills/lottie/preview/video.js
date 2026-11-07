// Renders a Lottie to an MP4 at its own frame rate with lottie-web (SVG renderer) in headless
// Chrome: every frame drawn and screenshotted, then stitched by ffmpeg.
//
//   node video.js <file.json> [--size 360] [--bg #DCE6F5] [--loops 2] [--out file.mp4]
//
// `--loops` repeats the animation back to back (a one-shot then reads as it would when replayed),
// with a short rest on the last frame between plays.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');

const HERE = __dirname;
const CHROME = require('./chrome');
const LOTTIE = path.join(HERE, 'node_modules/lottie-web/build/player/lottie_svg.min.js');

function parseArgs(argv) {
  const o = { name: null, size: 360, bg: '#DCE6F5', loops: 2, rest: 30, out: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--size') o.size = +argv[++i];
    else if (a === '--bg') o.bg = argv[++i];
    else if (a === '--loops') o.loops = +argv[++i];
    else if (a === '--rest') o.rest = +argv[++i];
    else if (a === '--out') o.out = argv[++i];
    else o.name = a;
  }
  return o;
}

(async () => {
  const opt = parseArgs(process.argv.slice(2));
  const file = path.resolve(opt.name);
  const name = path.basename(file, '.json');
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `lottie-${name}-`));
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: opt.size, height: opt.size, deviceScaleFactor: 1 });
    await page.setContent(`<!doctype html><html><body style="margin:0;background:${opt.bg}">
      <div id="b" style="width:${opt.size}px;height:${opt.size}px"></div></body></html>`);
    await page.addScriptTag({ path: LOTTIE });
    await page.evaluate((data) => new Promise((resolve) => {
      window.anim = lottie.loadAnimation({ container: document.getElementById('b'), renderer: 'svg',
        loop: false, autoplay: false, animationData: data });
      window.anim.addEventListener('DOMLoaded', resolve);
    }), data);
    const n = data.op - data.ip;
    for (let f = 0; f < n; f++) {
      await page.evaluate((f, op) => window.anim.goToAndStop(Math.min(f, op - 0.01), true), data.ip + f, data.op);
      await page.screenshot({ path: path.join(dir, `f${String(f).padStart(4, '0')}.png`) });
    }
    // one play, then the last frame held for `rest` frames, repeated `loops` times
    const list = [];
    for (let l = 0; l < opt.loops; l++) {
      for (let f = 0; f < n; f++) list.push(`f${String(f).padStart(4, '0')}.png`);
      for (let r = 0; r < opt.rest; r++) list.push(`f${String(n - 1).padStart(4, '0')}.png`);
    }
    const concat = list.map((f) => `file '${path.join(dir, f)}'\nduration ${1 / data.fr}`).join('\n');
    fs.writeFileSync(path.join(dir, 'list.txt'), concat + `\nfile '${path.join(dir, list[list.length - 1])}'\n`);
    const out = opt.out || path.join(process.cwd(), `${name}.mp4`);
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(dir, 'list.txt'),
      '-vf', `fps=${data.fr},format=yuv420p`, '-c:v', 'libx264', '-crf', '18', '-movflags', '+faststart', out]);
    console.log('wrote', out, `${n} frames @ ${data.fr} fps`);
  } finally {
    await browser.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
})();
