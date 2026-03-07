import * as React from "react";
import { useEffect, useState } from "react";
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
    
    // listen to global timeline tick
    window.addEventListener("timeline:tick", ((e: CustomEvent) => {
       w.Babulus._updateFrame(e.detail.frame, e.detail.fps);
    }) as EventListener);
  }

  // Use a dynamic import to avoid SSR errors.
  import("../../../../videos/scripts/browser-components").catch(e => {
    console.error("Failed to load browser components", e);
  });
}

// Workaround for module loading in Gatsby SSR/develop
let Player: any;
if (typeof window !== "undefined") {
  Player = require("@videoml/player/react").VideomlPlayer;
}

type VmlPreviewPlayerProps = {
  xmlPath: string;
};

export function VmlPreviewPlayer({ xmlPath }: VmlPreviewPlayerProps) {
  const [VideomlPlayerComponent, setVideomlPlayerComponent] = useState<any>(null);

  useEffect(() => {
    if (Player) {
      setVideomlPlayerComponent(() => Player);
    }
  }, []);

  const [xmlContent, setXmlContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const audioSrc = (() => {
    const match = xmlPath.match(/\/([^\/]+)\.babulus\.xml$/);
    return match ? `/videoml/${match[1]}.wav` : null;
  })();

  useEffect(() => {
    fetch("/" + xmlPath)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load VML file: " + res.statusText);
        return res.text();
      })
      .then((text) => setXmlContent(text))
      .catch((err) => setError(err.message));
  }, [xmlPath]);

  if (error) {
    return <div className="text-red-500 p-4">Error: {error}</div>;
  }

  if (!xmlContent || !VideomlPlayerComponent) {
    return <div className="text-muted p-4 flex flex-col items-center justify-center h-full min-h-[300px]">
      <div className="w-8 h-8 border-4 border-t-blue-500 border-r-transparent border-b-blue-500 border-l-transparent rounded-full animate-spin mb-4"></div>
      Loading preview...
    </div>;
  }

  return (
    <div className="relative w-full h-full flex flex-col bg-black">
      <div className="flex-1 relative overflow-hidden">
        <VideomlPlayerComponent
          xml={xmlContent}
          clockMode="bounded"
          loop={true}
          transport={{ mode: "always", keyboardShortcuts: true }}
          audioSrc={audioSrc ?? undefined}
        />
      </div>
    </div>
  );
}
