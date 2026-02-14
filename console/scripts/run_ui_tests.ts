import { spawn } from "child_process";
import { mkdtemp, cp, rm } from "fs/promises";
import { tmpdir } from "os";
import path from "path";
import { fileURLToPath } from "url";

const consoleRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
);
const fixtureSource = path.resolve(consoleRoot, "tests", "fixtures", "project");

function runCommand(command: string, args: string[], env: NodeJS.ProcessEnv) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: "inherit",
      env,
      cwd: consoleRoot
    });

    child.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} exited with code ${code}`));
      }
    });
  });
}

async function main() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "taskulus-console-"));
  const projectDir = path.join(tempDir, "project");
  await cp(fixtureSource, projectDir, { recursive: true });

  const env = {
    ...process.env,
    CONSOLE_PROJECT_ROOT: projectDir,
    CONSOLE_PORT: "5174",
    VITE_PORT: "5173"
  };

  try {
    await runCommand(
      "npx",
      ["start-server-and-test", "dev", "http://localhost:5173", "cucumber"],
      env
    );
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
