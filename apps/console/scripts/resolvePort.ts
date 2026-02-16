import net from "node:net";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

export type ResolvePortOptions = {
  desiredPort: number;
  serviceName: string;
  envVariable: string;
};

async function isPortAvailable(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const tester = net
      .createServer()
      .once("error", () => resolve(false))
      .once("listening", () => {
        tester.close(() => resolve(true));
      })
      .listen(port, "0.0.0.0");
  });
}

async function promptForIncrement(
  currentPort: number,
  incrementedPort: number,
  serviceName: string
): Promise<boolean> {
  if (!input.isTTY || !output.isTTY) {
    return false;
  }
  const rl = readline.createInterface({ input, output });
  const answer = await rl.question(
    `${serviceName} port ${currentPort} is already in use. Bump to ${incrementedPort}? [y/N] `
  );
  await rl.close();
  return answer.trim().toLowerCase().startsWith("y");
}

export async function resolvePortOrExit(
  options: ResolvePortOptions
): Promise<number> {
  const { desiredPort, serviceName, envVariable } = options;
  if (Number.isNaN(desiredPort) || desiredPort <= 0 || desiredPort >= 65535) {
    console.error(
      `${serviceName} port must be a valid number. Set ${envVariable} to a value between 1 and 65534.`
    );
    process.exit(1);
  }

  const available = await isPortAvailable(desiredPort);
  if (available) {
    return desiredPort;
  }

  const incrementedPort = desiredPort + 1;
  const accepted = await promptForIncrement(desiredPort, incrementedPort, serviceName);
  if (!accepted) {
    console.error(
      `${serviceName} cannot start on port ${desiredPort}. Exiting. Set ${envVariable} to a free port and retry.`
    );
    process.exit(1);
  }

  const incrementedAvailable = await isPortAvailable(incrementedPort);
  if (!incrementedAvailable) {
    console.error(
      `${serviceName} fallback port ${incrementedPort} is also in use. Set ${envVariable} to a free port and retry.`
    );
    process.exit(1);
  }

  return incrementedPort;
}
