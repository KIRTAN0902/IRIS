const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, shell, Notification, protocol, net, dialog } = require('electron');
const path = require('path');
const os = require('os');
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const url = require('url');
const {
  isTrustedAppUrl,
  normalizeExternalUrl,
  resolveFrontendAssetPath,
  isWithinDirectory,
} = require('./security.cjs');

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
let watchdogTimer = null;
let distWatcher = null;
let rendererRecoveryCount = 0;
let rendererRecoveryResetTimer = null;
let backendStartRetryDelayMs = 30_000;
let backendNextStartAt = 0;

const BACKEND_URL = 'http://127.0.0.1:8000/health';
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
    distWatcher = fs.watch(DIST_DIR, { recursive: true }, (eventType, filename) => {
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

app.on('second-instance', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    if (!mainWindow.isVisible()) mainWindow.show();
    mainWindow.focus();
  } else {
    createWindow();
  }
  ensureServices().catch(() => {});
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
  if (backendUp) {
    backendStartRetryDelayMs = 30_000;
    backendNextStartAt = 0;
    return;
  }
  if (Date.now() < backendNextStartAt) return;

  backendNextStartAt = Date.now() + backendStartRetryDelayMs;
  backendStartRetryDelayMs = Math.min(backendStartRetryDelayMs * 2, 5 * 60_000);
  log('Backend offline; attempting to start the IRIS backend daemon.');
  const vbsScript = path.join(REPO_ROOT, 'start-mesh-silent.vbs');
  if (fs.existsSync(vbsScript)) {
    try {
      const child = spawn('wscript.exe', [vbsScript], {
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
      child.once('error', (err) => log(`Backend start failed: ${err.name}`));
      child.unref();
      log('Spawned backend via start-mesh-silent.vbs');
    } catch (err) {
      log(`Backend start failed: ${err.name}`);
    }
  } else {
    log('Backend start script is unavailable.');
  }
}

// Watchdog: automatically restart backend if it goes down while IRIS desktop runs
watchdogTimer = setInterval(async () => {
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
    backgroundColor: '#f7f8fa',
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

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    log(`Renderer process exited: reason=${details.reason} exitCode=${details.exitCode}`);
    if (isQuitting || rendererRecoveryCount >= 3) {
      log('Renderer recovery limit reached; leaving the window stopped for user action.');
      return;
    }
    rendererRecoveryCount += 1;
    clearTimeout(rendererRecoveryResetTimer);
    rendererRecoveryResetTimer = setTimeout(() => { rendererRecoveryCount = 0; }, 60000);
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed() && !isQuitting) {
        log(`Reloading renderer after crash (attempt ${rendererRecoveryCount}/3).`);
        mainWindow.loadURL(APP_URL).catch((err) => log(`Renderer recovery load failed: ${err.name}`));
      }
    }, 800);
  });

  // Safety fallback: ensure window is displayed within 500ms
  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      mainWindow.show();
      mainWindow.focus();
    }
  }, 500);

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
    if (isTrustedAppUrl(openUrl)) {
      return { action: 'allow' };
    }
    const safeUrl = normalizeExternalUrl(openUrl);
    if (safeUrl) shell.openExternal(safeUrl).catch((err) => log(`External link open failed: ${err.name}`));
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, navigationUrl) => {
    if (!isTrustedAppUrl(navigationUrl)) {
      event.preventDefault();
      log('Blocked renderer navigation outside the IRIS app origin.');
    }
  });

  loadApp();
}

function loadApp() {
  mainWindow.loadURL(APP_URL);
  ensureServices().catch(() => {});
}

function triggerEmergencyKillSwitch(source = 'electron_global') {
  log(`[EMERGENCY KILL SWITCH] Triggered from: ${source}`);

  // 1. Direct local out-of-band sentinel signal (guaranteed <1ms, independent of HTTP/network)
  try {
    const signalFile = path.join(os.tmpdir(), 'iris_emergency_stop.signal');
    fs.writeFileSync(signalFile, JSON.stringify({ source, timestamp: Date.now() }), 'utf-8');
    log(`Out-of-band sentinel signal written to: ${signalFile}`);
  } catch (err) {
    log(`Warning: Failed to write emergency signal file: ${err.message}`);
  }

  // 2. HTTP secondary dispatch to local backend
  try {
    const postData = JSON.stringify({ source });
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 8000,
        path: '/api/computer/kill-switch',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData),
        },
        timeout: 2000,
      },
      (res) => {
        log(`Kill switch HTTP response: status ${res.statusCode}`);
      }
    );
    req.on('error', (err) => {
      log(`Kill switch HTTP request error: ${err.message}`);
    });
    req.write(postData);
    req.end();
  } catch (err) {
    log(`Kill switch invocation error: ${err}`);
  }

  if (Notification.isSupported()) {
    try {
      new Notification({
        title: '🚨 IRIS Computer Control STOPPED',
        body: 'Emergency Kill-Switch triggered. All active desktop operations aborted.',
        icon: PNG_ICON_PATH,
      }).show();
    } catch {}
  }

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('computer-kill-switch-engaged', { source });
  }
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
      label: '🚨 EMERGENCY KILL-SWITCH (Ctrl+Alt+K)',
      type: 'normal',
      click: () => triggerEmergencyKillSwitch('tray_menu'),
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

function isTrustedIpcSender(event) {
  return Boolean(
    mainWindow &&
    !mainWindow.isDestroyed() &&
    event.sender === mainWindow.webContents &&
    isTrustedAppUrl(event.senderFrame?.url || '')
  );
}

ipcMain.on('window-minimize', (event) => {
  if (isTrustedIpcSender(event)) mainWindow.minimize();
});

ipcMain.on('window-maximize', (event) => {
  if (isTrustedIpcSender(event)) {
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
  }
});

ipcMain.on('window-close', (event) => {
  if (isTrustedIpcSender(event)) mainWindow.hide();
});

ipcMain.handle('coding-select-directory', async (event) => {
  if (!isTrustedIpcSender(event)) return null;
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory', 'createDirectory'] });
  return result.canceled ? null : result.filePaths[0] || null;
});

ipcMain.handle('open-external', async (event, rawUrl) => {
  if (!isTrustedIpcSender(event)) return false;
  const safeUrl = normalizeExternalUrl(rawUrl);
  if (!safeUrl) return false;
  try {
    await shell.openExternal(safeUrl);
    return true;
  } catch (err) {
    log(`External link open failed: ${err.name}`);
    return false;
  }
});

ipcMain.handle('computer-trigger-kill-switch', async (event, source) => {
  if (!isTrustedIpcSender(event)) return false;
  triggerEmergencyKillSwitch(source || 'renderer_ui');
  return true;
});

app.whenReady().then(() => {
  // Register custom protocol handler for native iris://app execution
  protocol.handle('iris', async (request) => {
    const reqUrl = new URL(request.url);
    if (!isTrustedAppUrl(request.url)) {
      return new Response('Not found', { status: 404 });
    }

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
        log(`API proxy error path=${reqUrl.pathname} error=${err.name}`);
        return new Response(JSON.stringify({ error: {
          code: 'BACKEND_UNAVAILABLE',
          message: 'The IRIS backend is unavailable.',
          category: 'network',
          retryable: true,
        } }), {
          status: 502,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // 2. Resolve static assets from local build
    let filePath = resolveFrontendAssetPath(DIST_DIR, reqUrl.pathname);
    try {
      if (!filePath || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        filePath = path.join(DIST_DIR, 'index.html');
      } else {
        const realDist = fs.realpathSync(DIST_DIR);
        const realFile = fs.realpathSync(filePath);
        if (!isWithinDirectory(realDist, realFile)) filePath = path.join(DIST_DIR, 'index.html');
      }
    } catch {
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

  // Emergency Kill-Switch global shortcuts (model-independent hard stop)
  globalShortcut.register('CommandOrControl+Alt+K', () => {
    triggerEmergencyKillSwitch('global_shortcut_ctrl_alt_k');
  });

  globalShortcut.register('Pause', () => {
    triggerEmergencyKillSwitch('global_shortcut_pause');
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showWindow();
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  if (watchdogTimer) clearInterval(watchdogTimer);
  if (distWatcher) distWatcher.close();
  clearTimeout(rendererRecoveryResetTimer);
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', (event) => {
  event.preventDefault();
});
