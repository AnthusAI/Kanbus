import { createRequire } from "module";

type Args = {
  endpoint: string;
  authorizer: string;
  token: string;
  topic: string;
  timeoutMs: number;
  expectType?: string;
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

  const endpoint = args.endpoint ?? "";
  const authorizer = args.authorizer ?? "";
  const token = args.token ?? "";
  const topic = args.topic ?? "";
  const timeoutMs = Number(args.timeout_ms ?? "90000");
  const expectType = args.expect_type;

  if (!endpoint || !authorizer || !token || !topic || Number.isNaN(timeoutMs)) {
    throw new Error(
      "Usage: tsx scripts/cloud/probe_iot_mqtt.ts --endpoint <iot-endpoint> --authorizer <name> --token <kbt_...> --topic <topic> [--timeout_ms 90000] [--expect_type cloud_sync_completed]"
    );
  }

  return { endpoint, authorizer, token, topic, timeoutMs, expectType };
}

async function main() {
  const args = parseArgs(process.argv);
  const requireFromConsole = createRequire(`${process.cwd()}/package.json`);
  const mqtt = requireFromConsole("mqtt") as typeof import("mqtt");
  const url = `mqtts://${args.endpoint}:443`;
  const username = `?x-amz-customauthorizer-name=${encodeURIComponent(args.authorizer)}`;
  const clientId = `kbs-preaccept-${Date.now()}`;
  let settled = false;

  const done = (code: number, msg: string) => {
    if (settled) {
      return;
    }
    settled = true;
    if (msg) {
      process.stdout.write(`${msg}\n`);
    }
    process.exit(code);
  };

  const timer = setTimeout(() => {
    client.end(true);
    done(2, "timeout waiting for mqtt message");
  }, args.timeoutMs);

  const client = mqtt.connect(url, {
    clientId,
    username,
    password: args.token,
    protocolVersion: 4,
    connectTimeout: 15000,
    reconnectPeriod: 0,
    clean: true,
    rejectUnauthorized: true,
    ALPNProtocols: ["x-amzn-mqtt-ca"],
  });

  client.on("connect", () => {
    process.stdout.write(`connected topic=${args.topic}\n`);
    client.subscribe(args.topic, { qos: 0 }, (err) => {
      if (err) {
        clearTimeout(timer);
        client.end(true);
        done(3, `subscribe failed: ${String(err.message || err)}`);
      }
    });
  });

  client.on("message", (_topic, payload) => {
    clearTimeout(timer);
    const text = payload.toString("utf-8");
    try {
      const parsed = JSON.parse(text) as { type?: string };
      if (args.expectType && parsed.type !== args.expectType) {
        client.end(true);
        done(4, `message type mismatch: got=${parsed.type ?? "unknown"} expected=${args.expectType}`);
        return;
      }
      client.end(true);
      done(0, `message received: ${text}`);
    } catch {
      client.end(true);
      done(5, `message is not valid json: ${text}`);
    }
  });

  client.on("error", (error) => {
    clearTimeout(timer);
    client.end(true);
    done(6, `mqtt error: ${String(error.message || error)}`);
  });

  client.on("close", () => {
    if (!settled) {
      clearTimeout(timer);
      done(7, "mqtt connection closed before expected message");
    }
  });
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
