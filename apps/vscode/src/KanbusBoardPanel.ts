import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

export class KanbusBoardPanel {
  public static readonly viewType = "kanbus.board";

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private readonly serverPort: number;
  private disposables: vscode.Disposable[] = [];

  private onDidDisposeCallback?: () => void;

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    serverPort: number,
    onDidDisposeCallback?: () => void
  ) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.serverPort = serverPort;
    this.onDidDisposeCallback = onDidDisposeCallback;
    this.update();
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
  }

  public static create(
    extensionUri: vscode.Uri,
    serverPort: number,
    onDidDisposeCallback?: () => void
  ): KanbusBoardPanel {
    const panel = vscode.window.createWebviewPanel(
      KanbusBoardPanel.viewType,
      "Kanbus Board",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "console-assets"),
        ],
      }
    );
    return new KanbusBoardPanel(panel, extensionUri, serverPort, onDidDisposeCallback);
  }

  public reveal(): void {
    this.panel.reveal(vscode.ViewColumn.One);
  }

  get isDisposed(): boolean {
    return this._disposed;
  }
  private _disposed = false;

  private update(): void {
    try {
      this.panel.webview.html = this.getHtmlForWebview(this.panel.webview);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      try {
        this.panel.webview.html = `<html><body style="color:red;font-family:monospace;padding:20px">
          <h3>Kanbus: failed to load board</h3><pre>${message}</pre>
        </body></html>`;
      } catch {
        // Panel already disposed
      }
    }
  }

  private getHtmlForWebview(webview: vscode.Webview): string {
    const assetsDir = vscode.Uri.joinPath(this.extensionUri, "console-assets");
    const indexPath = path.join(assetsDir.fsPath, "index.html");
    let html = fs.readFileSync(indexPath, "utf8");

    // Nonce for the injected script
    const nonce = getNonce();
    const serverBase = `http://127.0.0.1:${this.serverPort}`;

    // Strip crossorigin attributes (webview can't do CORS pre-flight on its own resources)
    // Replace with a single space so adjacent attributes don't get concatenated
    html = html.replace(/\s+crossorigin(="[^"]*")?/gi, " ");

    // Rewrite /assets/... paths to vscode-webview-resource: URIs
    html = html.replace(
      /(src|href)="\/assets\/([^"]+)"/g,
      (_match, attr, file) => {
        const uri = webview.asWebviewUri(
          vscode.Uri.joinPath(assetsDir, "assets", file)
        );
        return `${attr}="${uri}"`;
      }
    );

    // Inject CSP meta tag (replace any existing one, or prepend to <head>)
    // webview.cspSource covers all vscode-webview-resource: URIs for bundled assets
    const csp = [
      `default-src 'none'`,
      `script-src 'nonce-${nonce}' ${webview.cspSource}`,
      `style-src ${webview.cspSource} 'unsafe-inline' https://fonts.googleapis.com`,
      `font-src https://fonts.gstatic.com`,
      `img-src ${webview.cspSource} data:`,
      `connect-src ${serverBase}`,
    ].join("; ");

    const cspTag = `<meta http-equiv="Content-Security-Policy" content="${csp}">`;
    if (html.includes("http-equiv=\"Content-Security-Policy\"")) {
      html = html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/i, cspTag);
    } else {
      html = html.replace("<head>", `<head>\n  ${cspTag}`);
    }

    // Inject patch script (theme + API redirect) before </head>
    const patchScript = this.buildPatchScript(nonce, serverBase);
    html = html.replace("</head>", `${patchScript}\n</head>`);

    return html;
  }

  private buildPatchScript(nonce: string, serverBase: string): string {
    return `<script nonce="${nonce}">
(function() {
  // ── Theme: map VSCode's body classes to prefers-color-scheme ──────────────
  // VSCode sets vscode-dark/vscode-light on <body>, but body may not exist yet
  // when this script runs (it's in <head>). Read from documentElement instead
  // via the data-vscode-theme-kind attribute that VSCode sets on <html>.
  function isDark() {
    var kind = document.documentElement.getAttribute("data-vscode-theme-kind");
    if (kind) {
      return kind === "vscode-dark" || kind === "vscode-high-contrast";
    }
    // Fallback: check body classes once body exists
    return document.body
      ? document.body.classList.contains("vscode-dark") ||
        document.body.classList.contains("vscode-high-contrast")
      : false;
  }

  // Override matchMedia so useAppearance's system mode reads VSCode's theme.
  // Return the real MediaQueryList but override only the .matches property
  // so all methods (addEventListener etc.) remain fully bound and functional.
  var _matchMedia = window.matchMedia.bind(window);
  window.matchMedia = function(query) {
    var mql = _matchMedia(query);
    if (query === "(prefers-color-scheme: dark)") {
      Object.defineProperty(mql, "matches", {
        get: function() { return isDark(); },
        configurable: true
      });
    }
    return mql;
  };

  // When VSCode switches theme, update the html class so React picks it up
  // via the existing matchMedia listener in useAppearance.
  document.addEventListener("DOMContentLoaded", function() {
    var observer = new MutationObserver(function() {
      var root = document.documentElement;
      root.classList.remove("light", "dark");
      root.classList.add(isDark() ? "dark" : "light");
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  });

  // ── API: redirect relative /api/* calls to kbsc server ───────────────────
  var serverBase = ${JSON.stringify(serverBase)};

  var _fetch = window.fetch.bind(window);
  window.fetch = function(input, init) {
    var url = typeof input === "string" ? input
            : input instanceof URL     ? input.href
            : input.url;
    if (url && url.startsWith("/api/")) {
      var rewritten = serverBase + url;
      if (typeof input === "string") {
        return _fetch(rewritten, init);
      } else if (input instanceof URL) {
        return _fetch(new URL(rewritten), init);
      } else {
        return _fetch(new Request(rewritten, input), init);
      }
    }
    return _fetch(input, init);
  };

  var _EventSource = window.EventSource;
  window.EventSource = function(url, opts) {
    if (typeof url === "string" && url.startsWith("/api/")) {
      url = serverBase + url;
    }
    return new _EventSource(url, opts);
  };
  window.EventSource.prototype = _EventSource.prototype;
  window.EventSource.CONNECTING = _EventSource.CONNECTING;
  window.EventSource.OPEN = _EventSource.OPEN;
  window.EventSource.CLOSED = _EventSource.CLOSED;

  // ── Stub sendBeacon — not available in vscode-webview-resource: origin ────
  // The console app uses sendBeacon for telemetry; stub it out silently so
  // it doesn't spam the DevTools console with errors.
  navigator.sendBeacon = function() { return false; };
})();
</script>`;
  }

  dispose(): void {
    if (this._disposed) { return; }
    this._disposed = true;
    this.onDidDisposeCallback?.();
    this.disposables.forEach((d) => d.dispose());
    this.disposables = [];
  }
}

function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let nonce = "";
  for (let i = 0; i < 32; i++) {
    nonce += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return nonce;
}
