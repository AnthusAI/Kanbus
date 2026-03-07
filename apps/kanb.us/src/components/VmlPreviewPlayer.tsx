import * as React from "react";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { spring, interpolate } from "remotion";

if (typeof window !== "undefined") {
  try {
    require("@webcomponents/custom-elements/src/native-shim.js");
    require("@videoml/stdlib/dom");
  } catch (e) {
    console.error("Failed to load @videoml/stdlib/dom or its polyfill", e);
  }
}

if (typeof window !== "undefined") {
  const w = window as any;
  if (!w.Babulus) {
    const frameTarget = new EventTarget();
    let currentFrame = 0;
    let currentFps = 24;

    w.Babulus = {
      components: new Map(),
      registerComponent: (name: string, Component: any) => {
        w.Babulus.components.set(name, Component);

        const kebabName = name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
        if (!customElements.get(kebabName)) {
          class ReactWrapper extends HTMLElement {
            private root: any = null;

            connectedCallback() {
              this.style.display = "block";
              this.style.width = "100%";
              this.style.height = "100%";
              this.style.position = "relative";
              this.root = createRoot(this);
              this.renderComponent();
            }

            disconnectedCallback() {
              this.root?.unmount();
              this.root = null;
            }

            attributeChangedCallback() {
              this.renderComponent();
            }

            static get observedAttributes() {
              return ["props"];
            }

            renderComponent() {
              if (!this.root) return;
              const props: any = {};
              try {
                const propsAttr = this.getAttribute("props");
                if (propsAttr) Object.assign(props, JSON.parse(propsAttr));
              } catch {
                // Ignore malformed props attributes.
              }
              this.root.render(React.createElement(Component, props));
            }
          }
          customElements.define(kebabName, ReactWrapper);
        }
      },
      listComponents: () => Array.from(w.Babulus.components.keys()),
      getComponent: (name: string) => w.Babulus.components.get(name),
      useCurrentFrame: () => {
        const [frame, setFrame] = useState(currentFrame);
        useEffect(() => {
          const handler = (e: any) => setFrame(e.detail);
          frameTarget.addEventListener("frame", handler);
          return () => frameTarget.removeEventListener("frame", handler);
        }, []);
        return frame;
      },
      useVideoConfig: () => ({ fps: currentFps, width: 1920, height: 1080, durationFrames: 240 }),
      spring: spring,
      interpolate: interpolate,
      _updateFrame: (frame: number, fps: number) => {
        currentFrame = frame;
        currentFps = fps;
        frameTarget.dispatchEvent(new CustomEvent("frame", { detail: frame }));
      },
    };

    window.addEventListener(
      "timeline:tick",
      ((e: CustomEvent) => {
        const detail = e.detail ?? {};
        const frame = Number.isFinite(detail.sceneLocalFrame)
          ? detail.sceneLocalFrame
          : Number.isFinite(detail.frame)
            ? detail.frame
            : 0;
        const fps = Number.isFinite(detail.fps) ? detail.fps : 24;
        w.Babulus._updateFrame(Math.max(0, Math.floor(frame)), fps);
      }) as EventListener,
    );
  }

  import("../../../../videos/scripts/browser-components").catch((e) => {
    console.error("Failed to load browser components", e);
  });
}

let CorePlayer: any;
if (typeof window !== "undefined") {
  try {
    const mod = require("@videoml/player/react");
    CorePlayer = mod?.VideomlPlayer ?? null;
  } catch {
    CorePlayer = null;
  }
}

type VmlPreviewPlayerProps = {
  videoId: string;
};

type PreviewHealth = {
  ok: boolean;
  videoId: string;
  xmlPath: string;
  xmlExists: boolean;
  xmlMtimeMs: number | null;
  wavPath: string;
  wavExists: boolean;
  wavMtimeMs: number | null;
};

export function VmlPreviewPlayer({ videoId }: VmlPreviewPlayerProps) {
  const [PlayerComponent, setPlayerComponent] = useState<any>(null);
  const [xmlContent, setXmlContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<PreviewHealth | null>(null);
  const xmlUrl = `/__vml/content/${videoId}.babulus.xml`;

  useEffect(() => {
    if (CorePlayer) {
      setPlayerComponent(() => CorePlayer);
      return;
    }
    setError(
      "Core VideoML transport player not found. Install a VideoML player build that exports `VideomlPlayer` from `@videoml/player/react`.",
    );
  }, []);

  useEffect(() => {
    if (!CorePlayer) return;
    let cancelled = false;
    setError(null);
    setHealth(null);
    setXmlContent(null);

    const loadPreviewAssets = async () => {
      try {
        const healthRes = await fetch(`/__vml/health/${videoId}`);
        if (!healthRes.ok) {
          if (healthRes.status === 404) {
            throw new Error(
              "Preview health endpoint failed (404). Restart `npm --prefix apps/kanb.us run develop` so Gatsby loads `onCreateDevServer` routes.",
            );
          }
          throw new Error(`Preview health endpoint failed (${healthRes.status})`);
        }

        const previewHealth = (await healthRes.json()) as PreviewHealth;
        if (cancelled) return;
        setHealth(previewHealth);

        if (!previewHealth.ok) {
          const missing = [];
          if (!previewHealth.xmlExists) missing.push(`XML missing: ${previewHealth.xmlPath}`);
          if (!previewHealth.wavExists) missing.push(`WAV missing: ${previewHealth.wavPath}`);
          const fixCmd =
            videoId === "intro"
              ? "node scripts/sync-vml-preview-assets.js --intro"
              : "node scripts/sync-vml-preview-assets.js --all";
          throw new Error(`${missing.join(" | ")}. Run: ${fixCmd}`);
        }

        const xmlRes = await fetch(xmlUrl);
        if (!xmlRes.ok) {
          throw new Error(`Failed to load XML ${xmlUrl} (${xmlRes.status})`);
        }
        const text = await xmlRes.text();
        if (!cancelled) {
          setXmlContent(text);
        }
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Preview load failed");
      }
    };

    loadPreviewAssets();
    return () => {
      cancelled = true;
    };
  }, [videoId, xmlUrl]);

  if (error) {
    const defaultFixCmd =
      videoId === "intro"
        ? "node scripts/sync-vml-preview-assets.js --intro"
        : "node scripts/sync-vml-preview-assets.js --all";
    return (
      <div className="h-full min-h-[300px] bg-[#160a0a] text-red-100 p-6 border border-red-600/70 rounded-lg overflow-auto">
        <div className="text-sm tracking-wide font-bold text-red-300">PREVIEW_INPUTS_MISSING</div>
        <div className="mt-3 text-base font-semibold">
          Preview cannot start for <code>{videoId}</code>.
        </div>
        <div className="mt-2 text-sm leading-6 text-red-100/90">{error}</div>
        <div className="mt-4 text-xs text-red-200/90 space-y-1">
          <div>
            Health endpoint: <code>/__vml/health/{videoId}</code>
          </div>
          {health ? <div>XML path: {health.xmlPath}</div> : null}
          {health ? <div>WAV path: {health.wavPath}</div> : null}
        </div>
        <div className="mt-5 rounded border border-red-500/70 bg-black/40 p-3 text-xs font-mono text-red-200">
          {defaultFixCmd}
        </div>
      </div>
    );
  }

  if (!xmlContent || !PlayerComponent) {
    return (
      <div className="text-muted p-4 flex flex-col items-center justify-center h-full min-h-[300px]">
        <div className="w-8 h-8 border-4 border-t-blue-500 border-r-transparent border-b-blue-500 border-l-transparent rounded-full animate-spin mb-4" />
        Loading preview...
      </div>
    );
  }

  return (
    <div className="relative w-full h-full bg-black">
      <PlayerComponent
        xml={xmlContent}
        autoPlay={false}
        clockMode="bounded"
        loop={true}
        width={1920}
        height={1080}
        audioSrc={`/videoml/${videoId}.wav`}
        transport={{ mode: "overlay-autohide", autoHideMs: 1600, keyboardShortcuts: true }}
      />
    </div>
  );
}
