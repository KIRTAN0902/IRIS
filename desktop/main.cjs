const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, shell, Notification } = require('electron');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');

const REPO_ROOT = 'C:\\kirtan\\IRIS';
const logFile = path.join(REPO_ROOT, 'desktop', 'iris-desktop.log');
function log(msg) {
  try {
    fs.appendFileSync(logFile, `[${new Date().toISOString()}] ${msg}\n`);
  } catch (e) {}
}

log('=== main.cjs loaded ===');
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

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:8000/health';

const ICON_PATH = path.join(__dirname, 'assets', 'icon.ico');
const PNG_ICON_PATH = path.join(__dirname, 'assets', 'icon.png');
const LOADING_HTML = path.join(__dirname, 'loading.html');

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
    try {
      const ok = await checkUrl(BACKEND_URL);
      if (ok) {
        mainWindow.webContents.reloadIgnoringCache();
      }
    } catch {}
  }
});

function checkUrl(url, timeoutMs = 4000) {
  return new Promise((resolve) => {
    try {
      const parsed = new URL(url);
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
  // 1. Ensure backend is running
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

  // 2. Ensure frontend Vite is running
  const frontendUp = await checkUrl(FRONTEND_URL);
  if (!frontendUp) {
    const vbsScript = path.join(REPO_ROOT, 'start-vite-silent.vbs');
    if (fs.existsSync(vbsScript)) {
      log('Starting IRIS frontend Vite dev server silently...');
      spawn('wscript.exe', [vbsScript], {
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      }).unref();
      log('Spawned frontend via start-vite-silent.vbs');
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

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://localhost') || url.startsWith('http://127.0.0.1')) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    if (validatedURL && validatedURL.includes('5173')) {
      mainWindow.loadFile(LOADING_HTML);
      pollAndConnect();
    }
  });

  loadApp();
}

let pollTimer = null;
function pollAndConnect() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const isReady = await checkUrl(FRONTEND_URL);
    if (isReady && mainWindow) {
      clearInterval(pollTimer);
      pollTimer = null;
      mainWindow.loadURL(FRONTEND_URL);
    }
  }, 1000);
}

async function loadApp() {
  ensureServices();
  const isViteReady = await checkUrl(FRONTEND_URL);
  if (isViteReady) {
    mainWindow.loadURL(FRONTEND_URL);
  } else {
    mainWindow.loadFile(LOADING_HTML);
    pollAndConnect();
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
      label: 'Reload UI (Ctrl+R)',
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
      label: 'Open in Browser (localhost:5173)',
      click: () => shell.openExternal(FRONTEND_URL),
    },
    {
      label: 'Check Backend Status',
      click: async () => {
        const ok = await checkUrl(BACKEND_URL);
        if (Notification.isSupported()) {
          try {
            new Notification({
              title: 'IRIS Backend Status',
              body: ok ? 'Backend & Mesh daemon are OPERATIONAL on port 8000.' : 'Backend on port 8000 is not responding.',
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
  createWindow();
  createTray();

  globalShortcut.register('Alt+I', () => {
    toggleWindow();
  });

  globalShortcut.register('CommandOrControl+Alt+I', () => {
    toggleWindow();
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
