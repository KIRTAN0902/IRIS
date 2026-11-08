const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('irisDesktop', {
  isDesktop: true,
  platform: process.platform,
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  openExternal: (url) => ipcRenderer.invoke('open-external', String(url)),
  selectProjectDirectory: () => ipcRenderer.invoke('coding-select-directory'),
  triggerKillSwitch: (source) => ipcRenderer.invoke('computer-trigger-kill-switch', source),
  resetKillSwitch: () => ipcRenderer.invoke('computer-reset-kill-switch'),
  onKillSwitchEngaged: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('computer-kill-switch-engaged', handler);
    return () => ipcRenderer.removeListener('computer-kill-switch-engaged', handler);
  },
  onOpenAgyDrawer: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('open-agy-drawer', handler);
    return () => ipcRenderer.removeListener('open-agy-drawer', handler);
  },
});
