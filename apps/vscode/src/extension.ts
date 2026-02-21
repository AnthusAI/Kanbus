import * as vscode from "vscode";
import { KbscProcess } from "./kbscProcess";
import { KanbusBoardPanel } from "./KanbusBoardPanel";

let kbscProcess: KbscProcess | undefined;
let boardPanel: KanbusBoardPanel | undefined;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel("Kanbus");

  const openBoardCommand = vscode.commands.registerCommand(
    "kanbus.openBoard",
    async () => {
      const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
      if (!workspaceFolder) {
        vscode.window.showErrorMessage("Kanbus: No workspace folder open.");
        return;
      }

      // Start kbsc if not running
      if (!kbscProcess || kbscProcess.port === null) {
        kbscProcess?.dispose();
        kbscProcess = new KbscProcess(outputChannel);
        try {
          await vscode.window.withProgress(
            {
              location: vscode.ProgressLocation.Notification,
              title: "Starting Kanbus server...",
              cancellable: false,
            },
            async () => {
              const port = await kbscProcess!.start(
                workspaceFolder.uri.fsPath
              );
              outputChannel.appendLine(`Kanbus server ready on port ${port}`);
            }
          );
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          vscode.window.showErrorMessage(`Kanbus: ${message}`);
          kbscProcess.dispose();
          kbscProcess = undefined;
          return;
        }
      }

      // Create or reveal the webview panel
      if (boardPanel && !boardPanel.isDisposed) {
        boardPanel.reveal();
      } else {
        boardPanel?.dispose();
        boardPanel = KanbusBoardPanel.create(
          context.extensionUri,
          kbscProcess.port!,
          () => { boardPanel = undefined; }
        );
      }
    }
  );

  context.subscriptions.push(openBoardCommand);
  context.subscriptions.push(outputChannel);
  context.subscriptions.push({
    dispose: () => {
      kbscProcess?.dispose();
      boardPanel?.dispose();
    },
  });
}

export function deactivate(): void {
  kbscProcess?.dispose();
  boardPanel?.dispose();
}
