import type { CapacitorConfig } from '@capacitor/cli';

const rawUrl =
  process.env.CAPACITOR_SERVER_URL ||
  process.env.VERCEL_URL ||
  process.env.VITE_VERCEL_URL ||
  'https://irisai.runs-on.dev/';

// Ensure protocol is present
const serverUrl = rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`;

const config: CapacitorConfig = {
  appId: 'com.kirtan.iris',
  appName: 'IRIS',
  webDir: 'dist',
  server: {
    url: serverUrl,
    cleartext: true,
    androidScheme: 'https',
  },
  android: {
    allowMixedContent: true,
  },
};

export default config;
