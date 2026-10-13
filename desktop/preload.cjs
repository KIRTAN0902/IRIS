const { contextBridge, ipcRenderer, shell } = require('electron');

contextBridge.exposeInMainWorld('irisDesktop', {
  isDesktop: true,
  platform: process.platform,
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  openExternal: (url) => shell.openExternal(url),
});
