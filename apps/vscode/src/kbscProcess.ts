import * as vscode from "vscode";
import * as cp from "child_process";
import * as net from "net";
import * as path from "path";
import * as fs from "fs";

export class KbscProcess implements vscode.Disposable {
  private process: cp.ChildProcess | null = null;
  private _port: number | null = null;
  private outputChannel: vscode.OutputChannel;

  get port(): number | null {
    return this._port;
  }

  constructor(outputChannel: vscode.OutputChannel) {
    this.outputChannel = outputChannel;
  }

  async start(workspaceFolder: string): Promise<number> {
    const config = vscode.workspace.getConfiguration("kanbus");
    const configPort = config.get<number>("port") || 0;
    const port = configPort || (await findFreePort());
    const kbscPath = this.resolveKbscPath();

    return new Promise((resolve, reject) => {
      this.outputChannel.appendLine(`Starting kbsc from: ${kbscPath}`);
      this.outputChannel.appendLine(`Workspace: ${workspaceFolder}`);
      this.outputChannel.appendLine(`Port: ${port}`);

      this.process = cp.spawn(kbscPath, [], {
        cwd: workspaceFolder,
        env: {
          ...process.env,
          CONSOLE_PORT: String(port),
        },
        stdio: ["ignore", "pipe", "pipe"],
      });

      let outputBuffer = "";
      this.process.stdout?.on("data", (data: Buffer) => {
        const text = data.toString();
        outputBuffer += text;
        this.outputChannel.appendLine(`[kbsc stdout] ${text.trim()}`);

        const match = outputBuffer.match(
          /Console backend listening on http:\/\/127\.0\.0\.1:(\d+)/
        );
        if (match) {
          this._port = parseInt(match[1], 10);
          resolve(this._port);
        }
      });

      this.process.stderr?.on("data", (data: Buffer) => {
        this.outputChannel.appendLine(`[kbsc stderr] ${data.toString().trim()}`);
      });

      this.process.on("error", (err) => {
        if ((err as NodeJS.ErrnoException).code === "ENOENT") {
          reject(
            new Error(
              `kbsc binary not found at "${kbscPath}". ` +
                `Install with: cargo install kanbus --bin kbsc`
            )
          );
        } else {
          reject(err);
        }
      });

      this.process.on("exit", (code) => {
        if (!this._port) {
          reject(new Error(`kbsc exited with code ${code} before starting`));
        }
        this.process = null;
        this._port = null;
      });

      setTimeout(() => {
        if (!this._port) {
          this.dispose();
          reject(new Error("kbsc did not start within 15 seconds"));
        }
      }, 15000);
    });
  }

  private resolveKbscPath(): string {
    // Look for bundled binary relative to the extension
    const extensionBin = path.join(__dirname, "..", "bin", "kbsc");
    if (fs.existsSync(extensionBin)) {
      return extensionBin;
    }
    // Fall back to PATH
    return "kbsc";
  }

  dispose(): void {
    if (this.process) {
      this.process.kill("SIGTERM");
      this.process = null;
    }
    this._port = null;
  }
}

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address() as net.AddressInfo;
      server.close(() => resolve(addr.port));
    });
    server.on("error", reject);
  });
}
