import { createRequire } from "module";

type Args = {
  appUrl: string;
  username: string;
  password: string;
  timeoutMs: number;
  eventDeadlineMs: number;
};

function parseArgs(argv: string[]): Args {
  const args: Record<string, string> = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key?.startsWith("--")) {
      continue;
    }
    if (!value || value.startsWith("--")) {
      args[key.slice(2)] = "true";
      i -= 1;
      continue;
    }
    args[key.slice(2)] = value;
  }

  const appUrl = args.app_url ?? "";
  const username = args.username ?? "";
  const password = args.password ?? "";
  const timeoutMs = Number(args.timeout_ms ?? "90000");
  const eventDeadlineMs = Number(args.event_deadline_ms ?? "60000");
  if (!appUrl || !username || !password || Number.isNaN(timeoutMs) || Number.isNaN(eventDeadlineMs)) {
    throw new Error(
      "Usage: tsx scripts/cloud/probe_browser_realtime.ts --app_url <url> --username <u> --password <p> [--timeout_ms 90000] [--event_deadline_ms 60000]"
    );
  }
  return { appUrl, username, password, timeoutMs, eventDeadlineMs };
}

async function maybeLogin(page: import("playwright").Page, username: string, password: string) {
  const loginField = page.locator('input[name="username"]');
  if (!(await loginField.isVisible().catch(() => false))) {
    return;
  }
  await loginField.fill(username);
  await page.locator('input[name="password"]').fill(password);
  await Promise.all([
    page.waitForLoadState("networkidle"),
    page.locator('input[name="signInSubmitButton"], button[type="submit"]').first().click(),
  ]);
}

async function main() {
  const args = parseArgs(process.argv);
  const requireFromConsole = createRequire(`${process.cwd()}/package.json`);
  const { chromium } = requireFromConsole("playwright") as typeof import("playwright");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  let mqttSubscribed = false;
  let usedSseFallback = false;
  let notificationReceived = false;
  let uiControlApplied = false;

  page.on("console", (msg) => {
    const text = msg.text();
    process.stdout.write(`[console] ${text}\n`);
    if (text.includes("[realtime] mqtt subscribed")) {
      mqttSubscribed = true;
    }
    if (text.includes("[realtime] using SSE fallback")) {
      usedSseFallback = true;
    }
    if (text.includes("[notifications] received")) {
      notificationReceived = true;
    }
    if (text.includes("[ui_control]")) {
      uiControlApplied = true;
    }
  });

  const started = Date.now();
  await page.goto(args.appUrl, { waitUntil: "domcontentloaded", timeout: args.timeoutMs });
  await maybeLogin(page, args.username, args.password);
  await page.waitForLoadState("networkidle", { timeout: args.timeoutMs });

  while (Date.now() - started < args.timeoutMs && !mqttSubscribed && !usedSseFallback) {
    await page.waitForTimeout(500);
  }

  if (!mqttSubscribed) {
    throw new Error("mqtt subscription was not observed");
  }
  if (usedSseFallback) {
    throw new Error("SSE fallback was observed; MQTT is not primary");
  }

  const eventStart = Date.now();
  while (
    Date.now() - eventStart < args.eventDeadlineMs &&
    !(notificationReceived && uiControlApplied)
  ) {
    await page.waitForTimeout(500);
  }

  if (!notificationReceived) {
    throw new Error("no realtime notification observed in browser logs");
  }
  if (!uiControlApplied) {
    throw new Error("ui_control action did not apply in browser logs");
  }

  await browser.close();
  process.stdout.write("browser realtime probe passed\n");
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
