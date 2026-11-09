// The server address is set at build time, never hard-coded:
//  - local development: EXPO_PUBLIC_API_URL in .env.local (e.g. http://192.168.x.x:5000)
//  - EAS builds: an EAS environment variable pointing at the Cloud Run HTTPS URL
const rawUrl = process.env.EXPO_PUBLIC_API_URL ?? '';

export const API_URL = rawUrl.replace(/\/+$/, '');

if (!API_URL) {
  console.warn('EXPO_PUBLIC_API_URL is not set. See README "Pointing the app at the server".');
}
