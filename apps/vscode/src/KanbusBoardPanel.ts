import * as vscode from "vscode";

export class KanbusBoardPanel {
  public static readonly viewType = "kanbus.board";

  private readonly panel: vscode.WebviewPanel;
  private readonly serverPort: number;
  private disposables: vscode.Disposable[] = [];

  private onDidDisposeCallback?: () => void;

  private constructor(
    panel: vscode.WebviewPanel,
    _extensionUri: vscode.Uri,
    serverPort: number,
    onDidDisposeCallback?: () => void
  ) {
    this.panel = panel;
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
        // Panel already disposed — nothing we can do
      }
    }
  }

  private getHtmlForWebview(_webview: vscode.Webview): string {
    const serverBase = `http://127.0.0.1:${this.serverPort}`;
    return `<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${serverBase}; style-src 'unsafe-inline';">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: transparent; }
    iframe { width: 100%; height: 100%; border: none; display: block; }
  </style>
</head>
<body>
  <iframe src="${serverBase}/" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"></iframe>
</body>
</html>`;
  }

  dispose(): void {
    if (this._disposed) { return; }
    this._disposed = true;
    this.onDidDisposeCallback?.();
    this.disposables.forEach((d) => d.dispose());
    this.disposables = [];
  }
}

