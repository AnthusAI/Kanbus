import { chromium } from "playwright-core";
import { execFileSync } from "node:child_process";

const consoleUrl = process.argv[2] ?? "http://localhost:4290/";
const fixtureRoot = process.argv[3];
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const instrumentation = () => {
  window.__perf = {
    longTasks: [],
    firstCardAt: null,
    firstCardPaintedAt: null,
    commits: [],
    lastServerEventAt: null,
    cardRenders: 0,
    columnRenders: 0,
    mutations: 0,
  };
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      window.__perf.longTasks.push({ start: entry.startTime, end: entry.startTime + entry.duration });
    }
  }).observe({ type: "longtask", buffered: true });

  const countFibers = (root) => {
    const cards = [];
    const columns = [];
    const visit = (fiber) => {
      let node = fiber;
      while (node) {
        const props = node.memoizedProps;
        const performedWork = (node.flags & 1) === 1 && node.alternate !== null;
        if (performedWork && props && typeof props === "object") {
          if ("issue" in props && "priorityName" in props) cards.push(props.issue.id);
          if ("columnKey" in props && "priorityLookup" in props) columns.push(props.columnKey);
        }
        if (node.child) visit(node.child);
        node = node.sibling;
      }
    };
    visit(root.current);
    return { cards, columns };
  };

  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true,
    renderers: new Map(),
    inject(renderer) {
      this.renderers.set(1, renderer);
      return 1;
    },
    onScheduleFiberRoot() {},
    onCommitFiberRoot(_id, root) {
      const counts = countFibers(root);
      window.__perf.commits.push({ at: performance.now(), ...counts });
    },
    onCommitFiberUnmount() {},
    checkDCE() {},
  };

  const NativeEventSource = window.EventSource;
  window.EventSource = class extends NativeEventSource {
    constructor(url, options) {
      super(url, options);
      this.addEventListener("message", () => {
        window.__perf.lastServerEventAt = performance.now();
      });
    }
  };
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (...args) => {
    const response = nativeFetch(...args);
    const url = String(args[0]?.url ?? args[0]);
    if (url.includes("/events")) {
      response.then(() => {
        window.__perf.lastServerEventAt = performance.now();
      });
    }
    return response;
  };

  const observer = new MutationObserver(() => {
    if (window.__perf.firstCardAt === null && document.querySelector(".issue-card")) {
      window.__perf.firstCardAt = performance.now();
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          window.__perf.firstCardPaintedAt = performance.now();
        })
      );
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  });
};

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--enable-precise-memory-info", "--disable-gpu"],
});
const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
const page = await context.newPage();
await page.addInitScript(instrumentation);

const resourceBytes = { script: 0 };
const loadedScripts = [];
page.on("response", async (response) => {
  const url = response.url();
  if (url.endsWith(".js")) {
    const body = await response.body().catch(() => null);
    if (body) {
      resourceBytes.script += body.length;
      loadedScripts.push(`${url.split("/").pop()} ${(body.length / 1024).toFixed(0)}kB`);
    }
  }
});

await page.goto(consoleUrl, { waitUntil: "commit" });
await page.waitForFunction(() => window.__perf.firstCardPaintedAt !== null, null, { timeout: 120000 });

await page.waitForFunction(
  () => {
    const now = performance.now();
    const tasks = window.__perf.longTasks;
    const lastEnd = tasks.length ? tasks[tasks.length - 1].end : 0;
    return now - Math.max(lastEnd, window.__perf.firstCardAt) > 2000;
  },
  null,
  { timeout: 120000, polling: 250 }
);

const loadMetrics = await page.evaluate(() => {
  const tasks = window.__perf.longTasks;
  const lastLongTaskEnd = tasks.length ? tasks[tasks.length - 1].end : 0;
  const firstCardAt = window.__perf.firstCardAt;
  const blocking = tasks.reduce((sum, task) => sum + Math.max(0, task.end - task.start - 50), 0);
  const heap = performance.memory ? performance.memory.usedJSHeapSize : null;
  return {
    firstCardMs: Math.round(firstCardAt),
    firstCardPaintedMs: Math.round(window.__perf.firstCardPaintedAt),
    timeToInteractiveMs: Math.round(Math.max(firstCardAt, lastLongTaskEnd)),
    totalBlockingMs: Math.round(blocking),
    longTaskCount: tasks.length,
    domNodes: document.querySelectorAll("*").length,
    issueCards: document.querySelectorAll(".issue-card").length,
    heapMb: heap ? Math.round(heap / 1048576) : null,
    url: location.href,
  };
});

const interactionMs = await page.evaluate(async () => {
  const header = document.querySelector(".kb-column-header");
  const before = performance.now();
  header.click();
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const first = performance.now() - before;
  const secondBefore = performance.now();
  header.click();
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  return Math.round(Math.max(first, performance.now() - secondBefore));
});

let realtime = null;
if (fixtureRoot) {
  const targetId = await page.evaluate(() => document.querySelector(".issue-card")?.getAttribute("data-issue-id"));
  await page.evaluate(() => {
    window.__perf.commits.length = 0;
    window.__perf.lastServerEventAt = null;
    window.__perf.longTasks.length = 0;
  });
  execFileSync("kbs", ["update", targetId, "--title", `Realtime probe ${Date.now()}`], {
    cwd: fixtureRoot,
    stdio: "ignore",
    env: { ...process.env, KANBUS_REALTIME_BROKER: "off", KANBUS_REALTIME_TRANSPORT: "off" },
  });
  await page.waitForFunction(() => window.__perf.commits.length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(3000);
  realtime = await page.evaluate(() => {
    const commits = window.__perf.commits;
    return {
      commitCount: commits.length,
      cardRenders: commits.reduce((sum, commit) => sum + commit.cards.length, 0),
      distinctCardsRendered: new Set(commits.flatMap((commit) => commit.cards)).size,
      columnRenders: commits.reduce((sum, commit) => sum + commit.columns.length, 0),
      distinctColumnsRendered: new Set(commits.flatMap((commit) => commit.columns)).size,
      mainThreadBlockedMs: Math.round(
        window.__perf.longTasks.reduce((sum, task) => sum + task.end - task.start, 0)
      ),
    };
  });
}

console.log(JSON.stringify({ loadMetrics, interactionMs, realtime, scriptKb: Math.round(resourceBytes.script / 1024), loadedScripts }, null, 2));
await browser.close();
