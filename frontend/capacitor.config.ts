import type { CapacitorConfig } from '@capacitor/cli';

// Bundle the same reviewed frontend that is built into the APK by default.
// A hosted WebView is still supported when a release explicitly supplies a URL.
const rawUrl = process.env.CAPACITOR_SERVER_URL?.trim();

// Ensure protocol is present
const serverUrl = rawUrl ? (rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`) : undefined;

const config: CapacitorConfig = {
  appId: 'com.kirtan.iris',
  appName: 'IRIS',
  webDir: 'dist',
  ...(serverUrl ? { server: { url: serverUrl, cleartext: true, androidScheme: 'https' as const } } : {}),
  android: {
    allowMixedContent: true,
  },
};

export default config;
