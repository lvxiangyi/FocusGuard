const { app, BrowserWindow, dialog, globalShortcut, Notification } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');
const http = require('http');

let mainWindow;
let backendProcess = null;
let BACKEND_PORT = 8899;

const dataEnv = process.env.AIMONITOR_DATA_ENV || 'prod';

function getSourceRoot() {
  return path.join(__dirname, '..');
}

function getAssetRoot() {
  return app.isPackaged ? process.resourcesPath : getSourceRoot();
}

function getAppDataRoot() {
  return process.env.AIMONITOR_APP_ROOT || (app.isPackaged ? app.getPath('userData') : getSourceRoot());
}

function getEnvFilePath() {
  if (process.env.AIMONITOR_ENV_FILE) {
    return process.env.AIMONITOR_ENV_FILE;
  }

  if (app.isPackaged) {
    const portableEnvPath = path.join(path.dirname(process.execPath), '.env');
    if (fs.existsSync(portableEnvPath)) {
      return portableEnvPath;
    }
    return path.join(getAppDataRoot(), '.env');
  }

  return path.join(getSourceRoot(), '.env');
}

function getLogsDir() {
  return path.join(getAppDataRoot(), 'data', dataEnv, 'logs');
}

function getAppLogPath() {
  return path.join(getLogsDir(), 'app.log');
}

function writeAppLog(message) {
  try {
    const logsDir = getLogsDir();
    const appLogPath = getAppLogPath();
    fs.mkdirSync(logsDir, { recursive: true });
    fs.appendFileSync(appLogPath, `[${new Date().toISOString()}] ${message}\n`, 'utf8');
  } catch (e) {
    console.error('[app] Failed to write app log:', e);
  }
}

function logInfo(message) {
  console.log(message);
  writeAppLog(message);
}

function logWarn(message) {
  console.warn(message);
  writeAppLog(message);
}

function logError(message, error) {
  console.error(message, error || '');
  writeAppLog(error ? `${message} ${error.stack || error}` : message);
}

function getFreePort(startPort = 8899) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.listen(startPort, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      resolve(getFreePort(startPort + 1));
    });
  });
}

function startBackend(port) {
  const backendDir = path.join(getAssetRoot(), 'backend');
  const packagedBackend = path.join(backendDir, 'aimonitor-backend.exe');
  const venvPython = path.join(backendDir, '.venv', 'Scripts', 'python.exe');
  let command = venvPython;
  let args = ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)];

  if (app.isPackaged && fs.existsSync(packagedBackend)) {
    command = packagedBackend;
    args = [];
  } else if (!fs.existsSync(venvPython)) {
    command = 'python';
    logWarn(`[backend] ${venvPython} was not found. Falling back to global "python". Run setup_windows.bat to create the project virtual environment.`);
  }

  backendProcess = spawn(
    command,
    args,
    {
      cwd: backendDir,
      shell: false,
      env: {
        ...process.env,
        FOCUSGUARD_PORT: String(port),
        AIMONITOR_DATA_ENV: process.env.AIMONITOR_DATA_ENV || 'prod',
        AIMONITOR_APP_ROOT: getAppDataRoot(),
        AIMONITOR_ENV_FILE: getEnvFilePath(),
      },
    },
  );

  backendProcess.stdout.on('data', (data) => {
    const message = `[backend] ${data}`;
    process.stdout.write(message);
    writeAppLog(message.trimEnd());
  });

  backendProcess.stderr.on('data', (data) => {
    const message = `[backend] ${data}`;
    process.stderr.write(message);
    writeAppLog(message.trimEnd());
  });

  backendProcess.on('error', (err) => {
    logError('[backend] Failed to start:', err);
  });

  backendProcess.on('exit', (code, signal) => {
    logInfo(`[backend] exited with code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

function renderMissingFrontendPage() {
  const message = [
    'Production frontend build not found.',
    '',
    'Run:',
    '  cd frontend',
    '  npm install',
    '  npm run build',
  ].join('\n');

  dialog.showErrorBox('FocusGuard frontend is not built', message);
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>FocusGuard setup needed</title>
        <style>
          body { margin: 0; font-family: Segoe UI, sans-serif; background: #111827; color: #f9fafb; display: grid; min-height: 100vh; place-items: center; }
          main { max-width: 680px; padding: 32px; }
          h1 { margin-top: 0; }
          pre { background: #030712; padding: 16px; border-radius: 8px; overflow: auto; }
        </style>
      </head>
      <body>
        <main>
          <h1>Frontend build not found</h1>
          <p>Run these commands from the repository root, then start the app again:</p>
          <pre>cd frontend
npm install
npm run build</pre>
        </main>
      </body>
    </html>
  `)}`);
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 820,
    height: 750,
    title: 'FocusGuard Agent',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    backgroundColor: '#0f0f23',
    autoHideMenuBar: true,
  });

  const apiBase = `http://127.0.0.1:${port}`;
  const frontendPath = path.join(getAssetRoot(), 'frontend', 'dist', 'index.html');

  if (process.env.AIMONITOR_ELECTRON_DEV === '1') {
    const devUrl = process.env.AIMONITOR_FRONTEND_DEV_URL || 'http://127.0.0.1:3000';
    mainWindow.loadURL(`${devUrl}?apiBase=${encodeURIComponent(apiBase)}`);
  } else if (fs.existsSync(frontendPath)) {
    mainWindow.loadFile(frontendPath, {
      query: { apiBase },
    });
  } else {
    renderMissingFrontendPage();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function waitForBackend(port, retries = 30) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const check = () => {
      attempts++;
      const req = http.get(`http://127.0.0.1:${port}/`, () => {
        resolve();
      });
      req.on('error', () => {
        if (attempts >= retries) {
          reject(new Error('Backend failed to start'));
        } else {
          setTimeout(check, 500);
        }
      });
      req.end();
    };

    check();
  });
}

function stopBackend() {
  if (!backendProcess) {
    return;
  }

  const pid = backendProcess.pid;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true });
  } else {
    backendProcess.kill('SIGTERM');
  }
  backendProcess = null;
}

function postJson(pathname, payload) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload || {});
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: BACKEND_PORT,
        path: pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => {
          if (res.statusCode >= 400) {
            reject(new Error(httpErrorMessage(data, res.statusCode)));
            return;
          }
          try {
            resolve(JSON.parse(data || '{}'));
          } catch (e) {
            resolve({});
          }
        });
      },
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function httpErrorMessage(data, statusCode) {
  if (!data) return `HTTP ${statusCode}`;
  try {
    const parsed = JSON.parse(data);
    const detail = parsed && parsed.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
    }
    if (detail) return JSON.stringify(detail);
  } catch (e) {
    // Backend sometimes returns plain text.
  }
  return data;
}

function notify(title, body) {
  try {
    if (Notification.isSupported()) {
      new Notification({ title, body }).show();
    }
  } catch (e) {
    logWarn(`[dataset] Notification failed: ${e}`);
  }
}

function getJson(pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get(
      {
        hostname: '127.0.0.1',
        port: BACKEND_PORT,
        path: pathname,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => {
          if (res.statusCode >= 400) {
            reject(new Error(httpErrorMessage(data, res.statusCode)));
            return;
          }
          try {
            resolve(JSON.parse(data || '{}'));
          } catch (e) {
            resolve({});
          }
        });
      },
    );
    req.on('error', reject);
  });
}

function refreshDatasetPending() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents
    .executeJavaScript("window.dispatchEvent(new CustomEvent('aimonitor-pending-capture'));")
    .catch((e) => logWarn(`[dataset] Could not refresh Dataset pending: ${e}`));
}

function registerDatasetShortcuts() {
  // Screenshot first. If a pending shot already exists, 1/2 only change 对/错.
  // Do not steal focus — recapturing after focusing Dataset would poison train.
  const shortcuts = [
    ['CommandOrControl+Alt+1', '对'],
    ['CommandOrControl+Alt+2', '错'],
  ];

  shortcuts.forEach(([accelerator, verdict]) => {
    const ok = globalShortcut.register(accelerator, async () => {
      try {
        const existing = await getJson('/personal-bench/pending-capture');
        let result;
        if (existing && existing.pending) {
          result = await postJson('/personal-bench/pending-capture/verdict', { verdict });
          notify('FocusGuard Data', `已标记：${verdict}（未重新截图，先到 Dataset 保存）`);
        } else {
          result = await postJson('/personal-bench/pending-capture', { verdict });
          const pending = result && result.pending ? result.pending : {};
          notify('FocusGuard Data', `已截图：${pending.verdict || verdict}。到 Dataset 填 context 后保存。`);
        }
        refreshDatasetPending();
      } catch (e) {
        logError(`[dataset] Hotkey capture failed for ${verdict}:`, e);
        notify('FocusGuard 截图失败', String(e.message || e));
      }
    });
    if (!ok) {
      logWarn(`[dataset] Failed to register shortcut ${accelerator}`);
    }
  });
}

app.whenReady().then(async () => {
  if (process.env.AIMONITOR_SKIP_BACKEND === '1') {
    BACKEND_PORT = Number(process.env.AIMONITOR_BACKEND_PORT || 8000);
    logInfo(`[app] Using existing backend on port ${BACKEND_PORT}`);
  } else {
    BACKEND_PORT = await getFreePort(8899);
    logInfo(`[app] Using port ${BACKEND_PORT}`);

    startBackend(BACKEND_PORT);
  }

  try {
    await waitForBackend(BACKEND_PORT);
    logInfo('[app] Backend is ready');
  } catch (e) {
    logError('[app] Backend failed to start, launching window anyway:', e);
  }

  createWindow(BACKEND_PORT);
  registerDatasetShortcuts();
});

app.on('window-all-closed', () => {
  stopBackend();
  app.quit();
});

app.on('before-quit', () => {
  globalShortcut.unregisterAll();
  stopBackend();
});
