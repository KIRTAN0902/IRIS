/* Layout probe: test horizontal overflow & bounding boxes across mobile and desktop viewports and primary routes. */
import puppeteer from "puppeteer-core";
import { existsSync } from "node:fs";

const edge = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => existsSync(p));

if (!edge) {
  console.error("Edge executable not found.");
  process.exit(1);
}

const viewports = [
  { width: 375, height: 812, name: "375x812 (Mobile iPhone SE/X)" },
  { width: 390, height: 844, name: "390x844 (Mobile iPhone 12/13/14/15)" },
  { width: 412, height: 915, name: "412x915 (Mobile Pixel/Galaxy)" },
  { width: 1366, height: 768, name: "1366x768 (Laptop Standard)" },
  { width: 1440, height: 900, name: "1440x900 (Desktop Medium)" },
  { width: 1920, height: 1080, name: "1920x1080 (Desktop FHD)" },
];

const routes = ["/", "/tasks", "/schedule", "/projects"];

const browser = await puppeteer.launch({
  executablePath: edge,
  headless: true,
  args: ["--disable-gpu", "--hide-scrollbars"],
});

let totalOffenders = 0;

try {
  for (const vp of viewports) {
    for (const route of routes) {
      const page = await browser.newPage();
      await page.setViewport({ width: vp.width, height: vp.height });
      await page.goto(`http://localhost:5173${route}`, { waitUntil: "networkidle2", timeout: 15000 });
      await new Promise((r) => setTimeout(r, 800));

      const report = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const scrollW = document.documentElement.scrollWidth;
        const bodyW = document.body.clientWidth;
        const offenders = [];
        for (const el of document.querySelectorAll("*")) {
          const r = el.getBoundingClientRect();
          if (r.width > vw + 1 || r.right > vw + 1) {
            offenders.push({
              tag: el.tagName,
              cls: String(el.className).slice(0, 80),
              w: Math.round(r.width),
              right: Math.round(r.right),
            });
          }
        }
        return { vw, scrollW, bodyW, offendersCount: offenders.length, offenders: offenders.slice(0, 5) };
      });

      console.log(`[${vp.name}] [${route}]: scrollW=${report.scrollW}, vw=${report.vw}, offenders=${report.offendersCount}`);
      if (report.offendersCount > 0) {
        totalOffenders += report.offendersCount;
        console.warn("  Offenders:", JSON.stringify(report.offenders, null, 2));
      }
      await page.close();
    }
  }
  console.log(`\nLayout probe finished with ${totalOffenders} total overflow offenders.`);
  if (totalOffenders > 0) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}


