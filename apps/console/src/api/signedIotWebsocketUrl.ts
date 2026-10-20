import { SignatureV4 } from "@aws-sdk/signature-v4";
import { Sha256 } from "@aws-crypto/sha256-js";
import { HttpRequest } from "@aws-sdk/protocol-http";
import { formatUrl } from "@aws-sdk/util-format-url";
import type { SigV4Credentials } from "./client";

export async function buildSignedIotWebsocketUrl(
  endpoint: string,
  region: string,
  credentials: SigV4Credentials
): Promise<string> {
  const request = new HttpRequest({
    protocol: "wss:",
    hostname: endpoint,
    method: "GET",
    path: "/mqtt",
    headers: {
      host: endpoint,
    },
  });
  const signer = new SignatureV4({
    service: "iotdevicegateway",
    region,
    sha256: Sha256,
    credentials: {
      accessKeyId: credentials.accessKeyId,
      secretAccessKey: credentials.secretAccessKey,
      sessionToken: credentials.sessionToken,
    },
  });
  const signed = await signer.presign(request, { expiresIn: 900 });
  return formatUrl(signed);
}
