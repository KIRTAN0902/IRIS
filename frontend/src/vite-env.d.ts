/// <reference types="vite/client" />

interface IrisDesktopBridge {
  isDesktop: boolean;
  platform: string;
  minimize: () => void;
  maximize: () => void;
  close: () => void;
  openExternal: (url: string) => void;
  onOpenAgyDrawer?: (callback: () => void) => () => void;
}

interface Window {
  irisDesktop?: IrisDesktopBridge;
}
