const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

function createWindow() {
  // El icono es opcional: si el archivo no existe, Electron usa el suyo.
  const icono = path.join(__dirname, 'icon.png');
  const opciones = {
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // La app es local; ver nota de seguridad en README.md
    },
  };
  if (fs.existsSync(icono)) opciones.icon = icono;

  const win = new BrowserWindow(opciones);
  win.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
