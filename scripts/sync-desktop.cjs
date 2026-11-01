const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const frontendDist = path.join(root, "frontend", "dist");
const packagedApp = path.join(
  root,
  "desktop",
  "dist",
  "IRIS-win32-x64",
  "resources",
  "app",
);

if (!fs.existsSync(path.join(frontendDist, "index.html"))) {
  throw new Error("Build frontend first; frontend/dist/index.html is missing.");
}
if (!fs.existsSync(path.join(packagedApp, "package.json"))) {
  throw new Error("Packaged Electron app is missing; desktop resource path was not found.");
}

fs.cpSync(frontendDist, path.join(packagedApp, "dist-frontend"), {
  recursive: true,
  force: true,
});
for (const filename of ["main.cjs", "preload.cjs", "security.cjs"]) {
  fs.copyFileSync(path.join(root, "desktop", filename), path.join(packagedApp, filename));
}

for (const filename of ["main.cjs", "preload.cjs", "security.cjs"]) {
  if (!fs.existsSync(path.join(packagedApp, filename))) {
    throw new Error(`Desktop sync did not install ${filename}.`);
  }
}
console.log("Synced frontend assets and Electron main/preload/security files.");
