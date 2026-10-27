const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisElectron', {
  isElectron: true,
  toggleAlwaysOnTop: () => ipcRenderer.invoke('jarvis:toggle-always-on-top'),
  toggleMiniMode: () => ipcRenderer.invoke('jarvis:toggle-mini-mode'),
  minimizeWindow: () => ipcRenderer.send('jarvis:minimize'),
  maximizeWindow: () => ipcRenderer.send('jarvis:maximize'),
  closeWindow: () => ipcRenderer.send('jarvis:close'),
});
