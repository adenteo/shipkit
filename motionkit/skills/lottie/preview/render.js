// Renders Lottie JSON contact sheets with lottie-web (SVG renderer) in headless Chrome.
//
//   node render.js <file.json | dir> ... [--n 24] [--size 150] [--bg #FFFFFF] [--out file.png]
//                  [--out-dir dir] [--frames 0,10,20]
//
// A directory means every .json inside it. Sheets go to ./previews/<name>.png unless --out or
// --out-dir says otherwise. Set CHROME_PATH if Chrome is not in a standard place.
//
// Frames are evenly spaced from ip to op inclusive, so a loop's last cell should match its first.
// The final cell is drawn at op - 0.01 because lottie-web hides a layer AT its op, while lottie-ios
// keeps a layer whose op equals the comp's op visible through the last frame.
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const HERE = __dirname;
const OUT = path.resolve(process.cwd(), 'previews');
const CHROME = require('./chrome');
const LOTTIE = path.join(HERE, 'node_modules/lottie-web/build/player/lottie_svg.min.js');

function parseArgs(argv) {
  const o = { names: [], n: null, size: 240, bg: '#DCE6F5', out: null, frames: null, cols: 4 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--n') o.n = +argv[++i];
    else if (a === '--size') o.size = +argv[++i];
    else if (a === '--bg') o.bg = argv[++i];
    else if (a === '--out') o.out = argv[++i];
    else if (a === '--out-dir') o.outDir = argv[++i];
    else if (a === '--cols') o.cols = +argv[++i];
    else if (a === '--frames') o.frames = argv[++i].split(',').map(Number);
    else o.names.push(a);
  }
  return o;
}

async function sheet(browser, name, opt) {
  const file = name.endsWith('.json') ? path.resolve(name) : path.resolve(name + '.json');
  name = path.basename(name, '.json');
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const n = opt.n || (data.op > 150 ? 16 : 12);
  const frames = opt.frames || Array.from({ length: n }, (_, i) => +(data.ip + (i * (data.op - data.ip)) / (n - 1)).toFixed(2));
  const cols = opt.frames ? Math.min(opt.cols, frames.length) : (n > 12 ? 4 : opt.cols);
  const size = opt.size;
  const kb = (fs.statSync(file).size / 1024).toFixed(1);
  const html = `<!doctype html><html><head><style>
    body{margin:0;padding:14px;background:#F2F2F4;font:600 13px -apple-system,Helvetica,sans-serif;color:#22222B}
    h1{font-size:15px;margin:0 0 10px 2px}
    .grid{display:grid;grid-template-columns:repeat(${cols},${size}px);gap:10px}
    .cell{background:${opt.bg};border-radius:10px;position:relative;width:${size}px;height:${size}px;overflow:hidden}
    .cell svg{display:block}
    .lab{position:absolute;left:6px;top:4px;font-size:11px;opacity:.55}
  </style></head><body><h1>${name} · ${data.op - data.ip} frames @ ${data.fr} fps (${((data.op - data.ip) / data.fr).toFixed(2)} s) · ${kb} KB</h1><div class="grid" id="g"></div></body></html>`;
  const page = await browser.newPage();
  const rows = Math.ceil(frames.length / cols);
  await page.setViewport({ width: cols * (size + 10) + 18, height: rows * (size + 10) + 60, deviceScaleFactor: 2 });
  await page.setContent(html);
  await page.addScriptTag({ path: LOTTIE });
  const errors = await page.evaluate((data, frames) => Promise.all(frames.map((f) => new Promise((resolve) => {
    const g = document.getElementById('g');
    const cell = document.createElement('div');
    cell.className = 'cell';
    const box = document.createElement('div');
    box.style.width = '100%';
    box.style.height = '100%';
    cell.appendChild(box);
    const lab = document.createElement('div');
    lab.className = 'lab';
    lab.textContent = 'f' + f;
    cell.appendChild(lab);
    g.appendChild(cell);
    const timer = setTimeout(() => resolve(`f${f}: never loaded (lottie-web rejected the data)`), 4000);
    try {
      const a = lottie.loadAnimation({ container: box, renderer: 'svg', loop: false, autoplay: false,
        animationData: JSON.parse(JSON.stringify(data)) });
      a.addEventListener('DOMLoaded', () => {
        clearTimeout(timer);
        a.goToAndStop(Math.min(f, data.op - 0.01), true);
        resolve(box.querySelectorAll('path').length ? null : `f${f}: rendered no paths`);
      });
    } catch (e) { clearTimeout(timer); resolve(`f${f}: ${e}`); }
  }))).then((r) => r.filter(Boolean)), data, frames);
  await new Promise((r) => setTimeout(r, 300));
  const out = opt.out || path.join(opt.outDir || OUT, `${name}.png`);
  await page.screenshot({ path: out, fullPage: true });
  await page.close();
  if (errors.length) { console.log(name, 'PROBLEMS', errors.slice(0, 3)); process.exitCode = 1; }
  console.log('wrote', out);
}

(async () => {
  const opt = parseArgs(process.argv.slice(2));
  let names = opt.names;
  if (!names.length) { console.error('usage: node render.js <file.json | dir> ...'); process.exit(2); }
  names = names.flatMap((n) => fs.statSync(n).isDirectory()
    ? fs.readdirSync(n).filter((f) => f.endsWith('.json')).map((f) => path.join(n, f)) : [n]);
  fs.mkdirSync(opt.outDir || OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  try {
    for (const name of names) await sheet(browser, name, opt);
  } finally {
    await browser.close();
  }
})();
