const { app, BrowserWindow, ipcMain, session, globalShortcut, screen } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

let mainWindow = null;
let serverProcess = null;
let isMiniMode = false;
let savedBounds = null;

const SERVER_URL = 'http://127.0.0.1:8000';
const ROOT_DIR = path.resolve(__dirname, '..');

function loadGeminiKey() {
  try {
    const desktopKeyPath = path.join(
      process.env.USERPROFILE || 'C:\\Users\\CAIO',
      'OneDrive',
      'Área de Trabalho',
      'GEMINI_API_KEY.txt'
    );
    if (fs.existsSync(desktopKeyPath)) {
      const raw = fs.readFileSync(desktopKeyPath, 'utf-8').trim();
      const val = raw.includes(':') ? raw.split(':').slice(1).join(':').trim() : raw;
      if (val) {
        process.env.GEMINI_API_KEY = val;
        process.env.GOOGLE_API_KEY = val;
      }
    }
  } catch (err) {
    // Ignore read errors
  }
}

function checkServerReady() {
  return new Promise((resolve) => {
    const req = http.get(`${SERVER_URL}/v1/speech/tts/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensureBackendRunning() {
  loadGeminiKey();
  const alreadyUp = await checkServerReady();
  if (alreadyUp) {
    return;
  }

  const jarvisExe = path.join(ROOT_DIR, '.venv', 'Scripts', 'jarvis.exe');
  const env = {
    ...process.env,
    PYTHONUTF8: '1',
    HF_HUB_DISABLE_SYMLINKS_WARNING: '1',
  };

  serverProcess = spawn(jarvisExe, ['serve', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: ROOT_DIR,
    env,
    windowsHide: true,
    stdio: 'ignore',
  });

  // Poll until server responds (up to 15 seconds)
  for (let i = 0; i < 30; i++) {
    const ready = await checkServerReady();
    if (ready) break;
    await new Promise((r) => setTimeout(r, 500));
  }
}

function createWindow() {
  // Auto-approve microphone & audio permissions for J.A.R.V.I.S. voice
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === 'media' || permission === 'audioCapture' || permission === 'notifications') {
      callback(true);
    } else {
      callback(true);
    }
  });

  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 420,
    minHeight: 540,
    title: 'J.A.R.V.I.S. — Stark Systems & Maestro HUB',
    backgroundColor: '#060d18',
    autoHideMenuBar: true,
    titleBarStyle: 'default',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(SERVER_URL);

  mainWindow.on('page-title-updated', (e) => {
    e.preventDefault();
    mainWindow.setTitle('J.A.R.V.I.S. — Stark Systems & Maestro HUB (Senhor Caio Renato)');
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('jarvis:toggle-always-on-top', () => {
  if (!mainWindow) return false;
  const next = !mainWindow.isAlwaysOnTop();
  mainWindow.setAlwaysOnTop(next, 'screen-saver');
  return next;
});

ipcMain.handle('jarvis:toggle-mini-mode', () => {
  if (!mainWindow) return false;
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: sw, height: sh } = primaryDisplay.workAreaSize;

  if (!isMiniMode) {
    savedBounds = mainWindow.getBounds();
    const miniW = 480;
    const miniH = 740;
    mainWindow.setBounds({
      x: Math.max(0, sw - miniW - 20),
      y: Math.max(0, sh - miniH - 20),
      width: miniW,
      height: miniH,
    });
    mainWindow.setAlwaysOnTop(true, 'screen-saver');
    isMiniMode = true;
  } else {
    if (savedBounds) {
      mainWindow.setBounds(savedBounds);
    } else {
      mainWindow.setSize(1320, 860);
      mainWindow.center();
    }
    mainWindow.setAlwaysOnTop(false);
    isMiniMode = false;
  }
  return isMiniMode;
});

ipcMain.on('jarvis:minimize', () => mainWindow?.minimize());
ipcMain.on('jarvis:maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('jarvis:close', () => mainWindow?.close());

app.whenReady().then(async () => {
  await ensureBackendRunning();
  createWindow();

  // Global shortcut Ctrl+Shift+J to summon/focus J.A.R.V.I.S. from anywhere in Windows
  try {
    globalShortcut.register('CommandOrControl+Shift+J', () => {
      if (!mainWindow) return;
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    });
  } catch (err) {
    // Ignore shortcut registration errors
  }
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  if (serverProcess) {
    try {
      serverProcess.kill();
    } catch (e) {}
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
