// Usage: node render.js stills 1.2,3.0,...   |   node render.js frames
const path = require("path");
const { chromium } = require("C:/Users/HP/AppData/Roaming/npm/node_modules/openclaw/node_modules/playwright-core");
const EXE = path.join(process.env.LOCALAPPDATA, "ms-playwright", "chromium-1234", "chrome-win64", "chrome.exe");
const FPS = 30, DURATION = 24.5;

(async () => {
  const mode = process.argv[2] || "frames";
  const browser = await chromium.launch({ executablePath: EXE, args: ["--allow-file-access-from-files", "--force-color-profile=srgb"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto("file:///" + path.join(__dirname, "video.html").replace(/\\/g, "/"));
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => i.onload = r))); });
  if (mode === "stills") {
    for (const t of process.argv[3].split(",").map(Number)) {
      await page.evaluate(t => window.render(t), t);
      await page.screenshot({ path: path.join(__dirname, `still-${t.toFixed(2)}.png`) });
    }
  } else {
    const n = Math.round(DURATION * FPS);
    for (let i = 0; i < n; i++) {
      await page.evaluate(t => window.render(t), i / FPS);
      await page.screenshot({ path: path.join(__dirname, "frames", `f${String(i).padStart(4, "0")}.jpg`), type: "jpeg", quality: 93 });
      if (i % 60 === 0) process.stdout.write(`${i}/${n} `);
    }
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
