import { createRequire } from "module";

type Args = {
  appUrl: string;
  username: string;
  password: string;
  expectedSyncSha: string;
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
  const expectedSyncSha = args.expected_sync_sha ?? "";
  const timeoutMs = Number(args.timeout_ms ?? "90000");
  const eventDeadlineMs = Number(args.event_deadline_ms ?? "60000");
  if (
    !appUrl
    || !username
    || !password
    || !expectedSyncSha
    || Number.isNaN(timeoutMs)
    || Number.isNaN(eventDeadlineMs)
  ) {
    throw new Error(
      "Usage: tsx scripts/cloud/probe_browser_realtime.ts --app_url <url> --username <u> --password <p> --expected_sync_sha <sha> [--timeout_ms 90000] [--event_deadline_ms 60000]"
    );
  }
  return { appUrl, username, password, expectedSyncSha, timeoutMs, eventDeadlineMs };
}

async function completeHostedUiLogin(
  page: import("playwright").Page,
  appUrl: string,
  username: string,
  password: string,
  timeoutMs: number
) {
  const appBase = new URL(appUrl);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const loginField = page.locator('input[name="username"]:visible').first();
    const passwordField = page.locator('input[name="password"]:visible').first();
    const submitButton = page.locator('input[name="signInSubmitButton"]:visible, button[type="submit"]:visible').first();
    if ((await loginField.count()) > 0 && (await passwordField.count()) > 0 && (await submitButton.count()) > 0) {
      await loginField.fill(username);
      await passwordField.fill(password);
      await submitButton.click();
      // Let Cognito redirect and app bootstrap proceed.
      await page.waitForTimeout(500);
      continue;
    }

    const url = page.url();
    if (url.startsWith(appBase.origin)) {
      const hasStoredAuth = await page.evaluate(() =>
        Boolean(window.localStorage.getItem("kanbus.console.cloudAuth"))
      );
      if (hasStoredAuth) {
        return;
      }
    }
    await page.waitForTimeout(500);
  }
  throw new Error("timed out completing Hosted UI login");
}

async function waitForInitialBoard(page: import("playwright").Page, timeoutMs: number): Promise<void> {
  await page.locator('[data-testid="board-view"]:visible').first().waitFor({
    state: "visible",
    timeout: timeoutMs,
  });
  await page.locator('[data-testid="board-view"]:visible [data-issue-id]').first().waitFor({
    state: "visible",
    timeout: timeoutMs,
  });
}

async function readBoardSignature(page: import("playwright").Page): Promise<{ count: number; signature: string }> {
  return page.locator('[data-testid="board-view"]:visible [data-issue-id]').evaluateAll((elements) => {
    const entries = elements
      .map((element) => {
        const issueId = element.getAttribute("data-issue-id") ?? "";
        const status = element.getAttribute("data-status") ?? "";
        const title =
          element.querySelector("h3")?.textContent?.trim().replace(/\s+/g, " ") ?? "";
        return `${issueId}|${status}|${title}`;
      })
      .filter((entry) => entry.length > 0)
      .sort();
    return {
      count: entries.length,
      signature: entries.join("\n"),
    };
  });
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
  let expectedSyncObserved = false;

  page.on("console", (msg) => {
    const text = msg.text();
    process.stdout.write(`[console] ${text}\n`);
    if (text.includes("[realtime] mqtt subscribed")) {
      mqttSubscribed = true;
    }
    if (text.includes("[realtime] using SSE fallback")) {
      usedSseFallback = true;
    }
    if (text.includes(`[notifications] cloud sync completed sha=${args.expectedSyncSha}`)) {
      expectedSyncObserved = true;
    }
  });

  const started = Date.now();
  await page.goto(args.appUrl, { waitUntil: "domcontentloaded", timeout: args.timeoutMs });
  await completeHostedUiLogin(page, args.appUrl, args.username, args.password, args.timeoutMs);
  await page.waitForLoadState("domcontentloaded", { timeout: args.timeoutMs });
  await waitForInitialBoard(page, args.timeoutMs);
  await page.waitForTimeout(1000);

  while (Date.now() - started < args.timeoutMs && !mqttSubscribed && !usedSseFallback) {
    await page.waitForTimeout(500);
  }

  if (!mqttSubscribed) {
    throw new Error("mqtt subscription was not observed");
  }
  if (usedSseFallback) {
    throw new Error("SSE fallback was observed; MQTT is not primary");
  }

  const initialBoard = await readBoardSignature(page);
  if (initialBoard.count === 0) {
    throw new Error("board rendered without any visible issue cards");
  }
  process.stdout.write(
    `initial board signature captured (${initialBoard.count} cards)\n`
  );

  const eventStart = Date.now();
  let boardDeltaObserved = false;
  while (
    Date.now() - eventStart < args.eventDeadlineMs &&
    !(expectedSyncObserved && boardDeltaObserved)
  ) {
    if (expectedSyncObserved) {
      const nextBoard = await readBoardSignature(page);
      if (nextBoard.signature !== initialBoard.signature) {
        boardDeltaObserved = true;
        process.stdout.write(
          `board signature changed after sync sha=${args.expectedSyncSha} (${initialBoard.count} -> ${nextBoard.count} cards)\n`
        );
        break;
      }
    }
    await page.waitForTimeout(500);
  }

  if (!expectedSyncObserved) {
    throw new Error(`expected cloud sync sha ${args.expectedSyncSha} was not observed`);
  }
  if (!boardDeltaObserved) {
    throw new Error(`sync sha ${args.expectedSyncSha} was observed but the board signature did not change`);
  }

  await browser.close();
  process.stdout.write("browser realtime probe passed\n");
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
