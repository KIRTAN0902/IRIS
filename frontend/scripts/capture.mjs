/* Capture review screenshots at exact device viewports. */
import puppeteer from "puppeteer-core";
import { existsSync, mkdirSync } from "node:fs";

const edge = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => existsSync(p));

const OUT = "../.impeccable/review";
mkdirSync(OUT, { recursive: true });

const shots = [
  { name: "desktop-home", url: "/", vp: { width: 1440, height: 900 } },
  { name: "desktop-today", url: "/today", vp: { width: 1440, height: 900 } },
  { name: "desktop-tasks", url: "/tasks", vp: { width: 1440, height: 900 } },
  { name: "desktop-startup", url: "/startup", vp: { width: 1440, height: 900 } },
  { name: "desktop-goals", url: "/goals", vp: { width: 1440, height: 900 } },
  { name: "desktop-schedule", url: "/schedule", vp: { width: 1440, height: 900 } },
  { name: "desktop-insights", url: "/insights", vp: { width: 1440, height: 900 } },
  { name: "desktop-modules", url: "/modules", vp: { width: 1440, height: 900 } },
  { name: "mobile-home", url: "/", vp: { width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 } },
  { name: "mobile-today", url: "/today", vp: { width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 } },
  { name: "mobile-startup", url: "/startup", vp: { width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 } },
];

const browser = await puppeteer.launch({
  executablePath: edge,
  headless: true,
  args: ["--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1"],
});

for (const s of shots) {
  const page = await browser.newPage();
  await page.setViewport(s.vp);
  await page.goto(`http://localhost:5173${s.url}`, { waitUntil: "networkidle2", timeout: 45000 });
  await new Promise((r) => setTimeout(r, 2200));
  await page.screenshot({ path: `${OUT}/${s.name}.png` });
  console.log("captured", s.name);
  await page.close();
}
await browser.close();
