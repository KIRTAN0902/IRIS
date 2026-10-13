const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, shell, Notification } = require('electron');
const path = require('path');
const http = require('http');

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
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

function checkUrl(url) {
  return new Promise((resolve) => {
    try {
      const parsed = new URL(url);
      const req = http.request(
        {
          host: parsed.hostname,
          port: parsed.port,
          path: parsed.pathname,
          method: 'GET',
          timeout: 1000,
        },
        (res) => {
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

  // Hide default menu bar for clean Notion look
  Menu.setApplicationMenu(null);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Intercept close button: minimize to tray instead of quitting
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();

      if (!hasNotifiedTray && Notification.isSupported()) {
        new Notification({
          title: 'IRIS is running in the background',
          body: 'Press Alt+I or click the tray icon anytime to open IRIS.',
          icon: PNG_ICON_PATH,
        }).show();
        hasNotifiedTray = true;
      }
    }
  });

  // Open external links in default OS browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://localhost') || url.startsWith('http://127.0.0.1')) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Handle connection errors
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    if (validatedURL && validatedURL.includes('5173')) {
      console.log('Frontend not reachable yet. Showing loading screen...');
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
      console.log('Vite frontend connected! Loading URL...');
      mainWindow.loadURL(FRONTEND_URL);
    }
  }, 1000);
}

async function loadApp() {
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
      console.warn('Tray icon could not be created:', err);
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
          new Notification({
            title: 'IRIS Backend Status',
            body: ok ? 'Backend & Mesh daemon are OPERATIONAL on port 8000.' : 'Backend on port 8000 is not responding.',
            icon: PNG_ICON_PATH,
          }).show();
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
  mainWindow.show();
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

// IPC controls
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

  // Register global hotkey Alt+I to toggle IRIS from anywhere in Windows
  const registered = globalShortcut.register('Alt+I', () => {
    toggleWindow();
  });

  if (!registered) {
    console.warn('Registration of global shortcut Alt+I failed.');
  }

  // Also register Ctrl+Alt+I as alternative
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
  // Prevent quitting when all windows are closed on Windows so tray persists
  event.preventDefault();
});
