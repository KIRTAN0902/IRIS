const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, shell, Notification, protocol, net } = require('electron');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const url = require('url');

// 1. Register custom standard scheme for native offline app execution
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'iris',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

const REPO_ROOT = 'C:\\kirtan\\IRIS';
const logFile = path.join(REPO_ROOT, 'desktop', 'iris-desktop.log');
function log(msg) {
  try {
    fs.appendFileSync(logFile, `[${new Date().toISOString()}] ${msg}\n`);
  } catch (e) {}
}

log('=== main.cjs loaded (Native Desktop Mode) ===');
app.name = 'IRIS';
try {
  app.setPath('userData', path.join(app.getPath('appData'), 'IRIS-Desktop'));
} catch (e) {
  log('Failed to set userData path: ' + e);
}

let mainWindow = null;
let tray = null;
let isQuitting = false;
let hasNotifiedTray = false;

const BACKEND_URL = 'http://localhost:8000/health';
const APP_URL = 'iris://app/index.html';

const ICON_PATH = path.join(__dirname, 'assets', 'icon.ico');
const PNG_ICON_PATH = path.join(__dirname, 'assets', 'icon.png');
const LOADING_HTML = path.join(__dirname, 'loading.html');

// Locate local distribution directory (prioritize live workspace build)
const candidateDistDirs = [
  path.join(REPO_ROOT, 'frontend', 'dist'),
  path.join(__dirname, '..', '..', '..', 'frontend', 'dist'),
  path.join(__dirname, '..', 'frontend', 'dist'),
  path.join(__dirname, 'dist-frontend'),
  path.join(__dirname, 'dist'),
];
const DIST_DIR = candidateDistDirs.find((d) => fs.existsSync(path.join(d, 'index.html'))) || path.join(REPO_ROOT, 'frontend', 'dist');
log('Using frontend distribution from: ' + DIST_DIR);

// Live Auto-Reload: Automatically reloads the desktop app the instant a frontend build completes
if (fs.existsSync(DIST_DIR)) {
  let reloadTimer = null;
  try {
    fs.watch(DIST_DIR, { recursive: true }, (eventType, filename) => {
      if (filename && (filename.endsWith('.html') || filename.endsWith('.js') || filename.endsWith('.css'))) {
        clearTimeout(reloadTimer);
        reloadTimer = setTimeout(() => {
          if (mainWindow && !mainWindow.isDestroyed()) {
            log('Detected frontend build update; auto-reloading desktop window...');
            mainWindow.reload();
          }
        }, 600);
      }
    });
    log('Watching ' + DIST_DIR + ' for live auto-updates.');
  } catch (err) {
    log('Failed to watch DIST_DIR: ' + err);
  }
}

// Ensure single instance
const gotTheLock = app.requestSingleInstanceLock();
log('requestSingleInstanceLock: ' + gotTheLock);
if (!gotTheLock) {
  log('Another instance is running. Exiting...');
  app.quit();
  process.exit(0);
}

app.on('second-instance', async () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    if (!mainWindow.isVisible()) mainWindow.show();
    mainWindow.focus();
    await ensureServices();
  }
});

function checkUrl(targetUrl, timeoutMs = 4000) {
  return new Promise((resolve) => {
    try {
      const parsed = new URL(targetUrl);
      const req = http.request(
        {
          host: parsed.hostname,
          port: parsed.port,
          path: parsed.pathname,
          method: 'GET',
          timeout: timeoutMs,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode >= 200 && res.statusCode < 400);
        }
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
      req.end();
    } catch {
      resolve(false);
    }
  });
}

async function ensureServices() {
  // Ensure local IRIS intelligence backend engine daemon is running
  const backendUp = await checkUrl(BACKEND_URL);
  if (!backendUp) {
    log('Backend offline; starting IRIS backend daemon...');
    const vbsScript = path.join(REPO_ROOT, 'start-mesh-silent.vbs');
    if (fs.existsSync(vbsScript)) {
      spawn('wscript.exe', [vbsScript], {
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      }).unref();
      log('Spawned backend via start-mesh-silent.vbs');
    }
  }
}

// Watchdog: automatically restart backend if it goes down while IRIS desktop runs
setInterval(async () => {
  const backendUp = await checkUrl(BACKEND_URL);
  if (!backendUp) {
    log('Watchdog: Backend offline on port 8000, resurrecting...');
    await ensureServices();
  }
}, 30000);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 900,
    minHeight: 620,
    title: 'IRIS',
    icon: ICON_PATH,
    backgroundColor: '#030712',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      spellcheck: true,
    },
  });

  Menu.setApplicationMenu(null);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();

      if (!hasNotifiedTray && Notification.isSupported()) {
        try {
          new Notification({
            title: 'IRIS is running in the background',
            body: 'Press Alt+I or click the tray icon anytime to open IRIS.',
            icon: PNG_ICON_PATH,
          }).show();
        } catch {
          // Ignore notification errors
        }
        hasNotifiedTray = true;
      }
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url: openUrl }) => {
    if (openUrl.startsWith('iris://') || openUrl.startsWith('http://localhost') || openUrl.startsWith('http://127.0.0.1')) {
      return { action: 'allow' };
    }
    shell.openExternal(openUrl);
    return { action: 'deny' };
  });

  loadApp();
}

async function loadApp() {
  await ensureServices();
  mainWindow.loadURL(APP_URL);
}

function createTray() {
  try {
    tray = new Tray(ICON_PATH);
  } catch (err) {
    try {
      tray = new Tray(PNG_ICON_PATH);
    } catch {
      return;
    }
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open IRIS',
      type: 'normal',
      click: () => showWindow(),
    },
    {
      label: 'Hide to Tray',
      type: 'normal',
      click: () => {
        if (mainWindow) mainWindow.hide();
      },
    },
    { type: 'separator' },
    {
      label: 'Open Antigravity Terminal (Alt+G)',
      type: 'normal',
      click: () => {
        showWindow();
        if (mainWindow) mainWindow.webContents.send('open-agy-drawer');
      },
    },
    { type: 'separator' },
    {
      label: 'Reload App (Ctrl+R)',
      click: () => {
        if (mainWindow) mainWindow.reload();
      },
    },
    {
      label: 'Toggle Developer Tools',
      click: () => {
        if (mainWindow) mainWindow.webContents.toggleDevTools();
      },
    },
    { type: 'separator' },
    {
      label: 'Check Backend Status',
      click: async () => {
        const ok = await checkUrl(BACKEND_URL);
        if (Notification.isSupported()) {
          try {
            new Notification({
              title: 'IRIS Backend Status',
              body: ok ? 'Local IRIS AI Engine is OPERATIONAL.' : 'Local IRIS AI Engine is starting...',
              icon: PNG_ICON_PATH,
            }).show();
          } catch {}
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit IRIS',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('IRIS - Intelligent Responsive Information System');
  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    toggleWindow();
  });

  tray.on('double-click', () => {
    showWindow();
  });
}

function showWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  if (!mainWindow.isVisible()) mainWindow.show();
  mainWindow.focus();
}

function toggleWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isVisible() && mainWindow.isFocused()) {
    mainWindow.hide();
  } else {
    showWindow();
  }
}

ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.hide();
});

app.whenReady().then(() => {
  // Register custom protocol handler for native iris://app execution
  protocol.handle('iris', async (request) => {
    const reqUrl = new URL(request.url);

    // 1. Transparently proxy /api/ calls directly to local backend daemon
    if (reqUrl.pathname.startsWith('/api/')) {
      const targetUrl = 'http://127.0.0.1:8000' + reqUrl.pathname + reqUrl.search;
      try {
        const fetchOpts = {
          method: request.method,
          headers: request.headers,
        };
        if (request.method !== 'GET' && request.method !== 'HEAD') {
          fetchOpts.body = request.body;
          fetchOpts.duplex = 'half';
        }
        return await net.fetch(targetUrl, fetchOpts);
      } catch (err) {
        log('API proxy error (' + targetUrl + '): ' + err.message);
        return new Response(JSON.stringify({ error: err.message }), {
          status: 502,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // 2. Resolve static assets from local build
    let relPath = reqUrl.pathname.replace(/^\/+/, '');
    let filePath = path.join(DIST_DIR, relPath);
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST_DIR, 'index.html');
    }
    return net.fetch(url.pathToFileURL(filePath).toString());
  });

  createWindow();
  createTray();

  globalShortcut.register('Alt+I', () => {
    toggleWindow();
  });

  globalShortcut.register('CommandOrControl+Alt+I', () => {
    toggleWindow();
  });

  globalShortcut.register('Alt+G', () => {
    showWindow();
    if (mainWindow) mainWindow.webContents.send('open-agy-drawer');
    log('Alt+G: requested Antigravity drawer');
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', (event) => {
  event.preventDefault();
});
