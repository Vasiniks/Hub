// Where the verification scripts point, and what they drive.
//
// ROOM_URL chooses the server — the dev server by default, so an unset environment behaves as it
// always has, `ROOM_URL=http://127.0.0.1:4173` runs the same checks against `vite preview`'s
// production bundle. CHROME_PATH chooses the browser, falling back to Playwright's own Chromium
// when the installed Chrome is missing (its app path moves between versions).
import fs from 'node:fs';
import { chromium } from 'playwright-core';

const installed = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

/** Origin with no trailing slash: callers append `/?debug&…`. */
export const base = (process.env.ROOM_URL ?? 'http://127.0.0.1:5173').replace(/\/+$/, '');
export const chrome = process.env.CHROME_PATH ?? (fs.existsSync(installed) ? installed : chromium.executablePath());
