// Finds a Chrome or Chromium for puppeteer-core. Set CHROME_PATH to override.
const fs = require('fs');
const candidates = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);
const found = candidates.find((p) => fs.existsSync(p));
if (!found) {
  console.error('No Chrome found. Install Chrome or set CHROME_PATH.');
  process.exit(2);
}
module.exports = found;
