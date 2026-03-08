import * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { spring, interpolate } from "remotion";

// Try to register the dom library here so that it gets loaded on the client side only
// to avoid SSR issues with custom elements
if (typeof window !== "undefined") {
  try {
    // In React 18 / Gatsby environments, typical ES5 adapters don't always bind perfectly
    // with Reflect.construct since HTMLElement requires 'new'.
    require("@webcomponents/custom-elements/src/native-shim.js");
    require("@videoml/stdlib/dom");
  } catch (e) {
    console.error("Failed to load @videoml/stdlib/dom or its polyfill", e);
  }
}

// Dynamically load to avoid SSR
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
        
        // Also register as a Web Component so VideoML DOM player can render it
        const kebabName = name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
        if (!customElements.get(kebabName)) {
           class ReactWrapper extends HTMLElement {
             private root: any = null;
             
             connectedCallback() {
               // Ensure custom element takes up the full container like native VML elements
               this.style.display = 'block';
               this.style.width = '100%';
               this.style.height = '100%';
               this.style.position = 'relative';
               
               // Must use createRoot for React 18
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
               return ['props'];
             }
             
             renderComponent() {
               if (!this.root) return;
               const props: any = {};
               try {
                 const propsAttr = this.getAttribute('props');
                 if (propsAttr) Object.assign(props, JSON.parse(propsAttr));
               } catch (e) {}
               this.root.render(React.createElement(Component, props));
             }
           }
           customElements.define(kebabName, ReactWrapper);
        }
      },
      listComponents: () => Array.from(w.Babulus.components.keys()),
      getComponent: (name: string) => w.Babulus.components.get(name),
      // Mocks for components to not crash when trying to use Remotion hooks
      useCurrentFrame: () => {
        const [frame, setFrame] = useState(currentFrame);
        useEffect(() => {
          const handler = (e: any) => setFrame(e.detail);
          frameTarget.addEventListener('frame', handler);
          return () => frameTarget.removeEventListener('frame', handler);
        }, []);
        return frame;
      },
      useVideoConfig: () => ({ fps: currentFps, width: 1920, height: 1080, durationFrames: 240 }),
      spring: spring,
      interpolate: interpolate,
      _updateFrame: (frame: number, fps: number) => {
        currentFrame = frame;
        currentFps = fps;
        frameTarget.dispatchEvent(new CustomEvent('frame', { detail: frame }));
      }
    };
    
    // listen to global timeline tick — use scene-local frame so component
    // animations start from 0 at the beginning of each scene
    window.addEventListener("timeline:tick", ((e: CustomEvent) => {
       const localFrame = e.detail.sceneLocalFrame ?? e.detail.frame;
       w.Babulus._updateFrame(localFrame, e.detail.fps);
    }) as EventListener);
  }

  // Use a dynamic import to avoid SSR errors.
  import("../../../../videos/scripts/browser-components").catch(e => {
    console.error("Failed to load browser components", e);
  });
}

type VmlPreviewPlayerProps = {
  xmlPath: string;
};

export function VmlPreviewPlayer({ xmlPath }: VmlPreviewPlayerProps) {
  const [VideomlPlayerComponent, setVideomlPlayerComponent] = useState<any>(null);

  useEffect(() => {
    import("@videoml/player/react").then((mod: any) => {
      const Player = mod.VideomlPlayer ?? mod.VideomlDomPlayer;
      if (Player) {
        setVideomlPlayerComponent(() => Player);
      } else {
        console.error("[VmlPreviewPlayer] No player found in module", Object.keys(mod));
      }
    }).catch((e: unknown) => {
      console.error("[VmlPreviewPlayer] Failed to load player", e);
    });
  }, []);

  const [xmlContent, setXmlContent] = useState<string | null>(null);
  const [timingOverlay, setTimingOverlay] = useState<string | null>(null);
  const [timingLoaded, setTimingLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const videoId = (() => {
    const match = xmlPath.match(/([^\/]+)\.babulus\.xml$/);
    return match ? match[1] : null;
  })();

  const audioSrc = videoId ? `/videoml/${videoId}.wav` : null;

  useEffect(() => {
    fetch("/" + xmlPath)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load VML file: " + res.statusText);
        return res.text();
      })
      .then((text) => setXmlContent(text))
      .catch((err) => setError(err.message));
  }, [xmlPath]);

  // Load the generated timing overlay for audio-measured scene timing.
  // Block player render until the fetch completes (success or 404) so the
  // player never mounts without timing — which would show the wrong scene.
  const timingPath = videoId ? `/videoml/${videoId}.timing.xml` : null;
  useEffect(() => {
    if (!timingPath) { setTimingLoaded(true); return; }
    fetch(timingPath)
      .then((res) => res.ok ? res.text() : null)
      .then((text) => { setTimingOverlay(text); setTimingLoaded(true); })
      .catch(() => { setTimingOverlay(null); setTimingLoaded(true); });
  }, [timingPath]);

  if (error) {
    return <div className="text-red-500 p-4">Error: {error}</div>;
  }

  // Merge timing overlay into the original XML string before mounting the player.
  // We parse only the overlay DOM (small, clean) to extract ids+attrs, then inject
  // those attributes into the original XML string via regex — preserving the exact
  // XML format that the player's VML parser (executeVomXml) expects.
  const mergedXml = useMemo(() => {
    if (!xmlContent) return null;
    if (!timingOverlay) return xmlContent;
    try {
      const overlayDoc = new DOMParser().parseFromString(timingOverlay, "text/html");
      let result = xmlContent;
      for (const overlayEl of Array.from(overlayDoc.querySelectorAll("[id]"))) {
        const id = overlayEl.getAttribute("id");
        if (!id) continue;
        const attrsToInject = Array.from(overlayEl.attributes)
          .filter(a => a.name !== "id")
          .map(a => `${a.name}="${a.value}"`)
          .join(" ");
        if (!attrsToInject) continue;
        // Use overlay element's tag name so that e.g. <cue id="cta"> doesn't
        // overwrite the timing already injected into <scene id="cta">.
        const tagName = overlayEl.tagName.toLowerCase();
        const escapedId = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        result = result.replace(
          new RegExp(`(<${tagName}\\b[^>]*\\bid="${escapedId}"[^>]*?)(\\s*\\/?>)`, 'i'),
          (_match, tagBody, close) => {
            const cleaned = tagBody
              .replace(/\s+start="[^"]*"/g, '')
              .replace(/\s+end="[^"]*"/g, '');
            return `${cleaned} ${attrsToInject}${close}`;
          }
        );
      }
      return result;
    } catch {
      return xmlContent;
    }
  }, [xmlContent, timingOverlay]);

  if (!mergedXml || !VideomlPlayerComponent || !timingLoaded) {
    return <div className="text-muted p-4 flex flex-col items-center justify-center h-full min-h-[300px]">
      <div className="w-8 h-8 border-4 border-t-blue-500 border-r-transparent border-b-blue-500 border-l-transparent rounded-full animate-spin mb-4"></div>
      Loading preview...
    </div>;
  }

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black">
      <VideomlPlayerComponent
        xml={mergedXml}
        clockMode="bounded"
        loop={true}
        transport={{ mode: "always", keyboardShortcuts: true }}
        audioSrc={audioSrc ?? undefined}
      />
    </div>
  );
}
