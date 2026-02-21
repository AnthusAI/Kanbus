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

    // Rewrite /assets/... paths to webview URIs and strip crossorigin attributes
    html = html.replace(
      /\s*crossorigin\s*(="[^"]*")?/gi,
      ""
    );
    html = html.replace(
      /(src|href)="\/assets\/([^"]+)"/g,
      (_match, attr, file) => {
        const uri = webview.asWebviewUri(
          vscode.Uri.joinPath(assetsDir, "assets", file)
        );
        return `${attr}="${uri}"`;
      }
    );

    // Inject our patch script before the closing </head>
    const serverBase = `http://127.0.0.1:${this.serverPort}`;
    const patchScript = this.buildPatchScript(serverBase);
    html = html.replace("</head>", `${patchScript}\n</head>`);

    return html;
  }

  private buildPatchScript(serverBase: string): string {
    return `<script>
(function() {
  // ── Theme: map VSCode's body classes to prefers-color-scheme ──────────────
  function isDark() {
    return document.body.classList.contains("vscode-dark") ||
           document.body.classList.contains("vscode-high-contrast");
  }

  var _matchMedia = window.matchMedia.bind(window);
  window.matchMedia = function(query) {
    var result = _matchMedia(query);
    if (query === "(prefers-color-scheme: dark)") {
      var dark = isDark();
      var overridden = Object.create(result);
      Object.defineProperty(overridden, "matches", { get: function() { return isDark(); } });
      return overridden;
    }
    return result;
  };

  // When VSCode switches theme, update the html class so React re-renders
  var observer = new MutationObserver(function() {
    var root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(isDark() ? "dark" : "light");
  });
  observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });

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
