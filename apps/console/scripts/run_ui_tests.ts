import { spawn } from "child_process";
import { mkdtemp, cp, rm, writeFile, access } from "fs/promises";
import { tmpdir } from "os";
import path from "path";
import { fileURLToPath } from "url";

const consoleRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
);
const repoRoot = path.resolve(consoleRoot, "../..");
const pythonPath = path.join(repoRoot, "python", "src");
const fixtureSource = path.resolve(consoleRoot, "tests", "fixtures", "project");

function runCommand(
  command: string,
  args: string[],
  env: NodeJS.ProcessEnv,
  cwd: string = consoleRoot
) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: "inherit",
      env,
      cwd
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

async function ensureUiBuild(env: NodeJS.ProcessEnv) {
  const uiRoot = path.resolve(repoRoot, "packages", "ui");
  const distEntry = path.join(uiRoot, "dist", "index.js");
  try {
    await access(distEntry);
    return;
  } catch {
    // Build is required.
  }
  await runCommand("npm", ["install"], env, uiRoot);
  await runCommand("npm", ["run", "build"], env, uiRoot);
}

async function main() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "kanbus-console-"));
  const projectDir = path.join(tempDir, "project");
  await cp(fixtureSource, projectDir, { recursive: true });
  const configurationPath = path.join(tempDir, ".kanbus.yml");
  await writeFile(
    configurationPath,
    "project_directory: project\nproject_key: kanbus\n",
    "utf-8"
  );

  const env = {
    ...process.env,
    CONSOLE_PROJECT_ROOT: projectDir,
    CONSOLE_PORT: process.env.CONSOLE_PORT ?? "5174",
    VITE_PORT: process.env.VITE_PORT ?? "5173",
    CONSOLE_BASE_URL:
      process.env.CONSOLE_BASE_URL ??
      `http://localhost:${process.env.VITE_PORT ?? "5173"}/`,
    CONSOLE_API_BASE:
      process.env.CONSOLE_API_BASE ??
      `http://localhost:${process.env.CONSOLE_PORT ?? "5174"}/api`,
    KANBUS_PYTHON: process.env.KANBUS_PYTHON ?? "python3",
    KANBUS_PYTHONPATH: process.env.KANBUS_PYTHONPATH ?? pythonPath
  };
  const vitePort = env.VITE_PORT ?? "5173";

  try {
    await ensureUiBuild(env);
    await runCommand(
      "npx",
      [
        "start-server-and-test",
        "dev",
        `http://localhost:${vitePort}`,
        "cucumber"
      ],
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
