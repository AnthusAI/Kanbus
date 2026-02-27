import * as React from "react";
import { useEffect, useState, useRef } from "react";
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
  Player = require("@videoml/player/react").VideomlDomPlayer;
}

type VmlPreviewPlayerProps = {
  xmlPath: string;
};

export function VmlPreviewPlayer({ xmlPath }: VmlPreviewPlayerProps) {
  const [VideomlDomPlayerComponent, setVideomlDomPlayerComponent] = useState<any>(null);

  useEffect(() => {
    if (Player) {
      setVideomlDomPlayerComponent(() => Player);
    }
  }, []);

  const [xmlContent, setXmlContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(10); // Default duration, the player should ideally tell us, but let's see.

  const audioRef = useRef<HTMLAudioElement>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);

  useEffect(() => {
    // Determine the audio source from xmlPath, e.g., "content/local-tasks.babulus.xml" -> "/videoml/local-tasks.wav"
    // The VML CLI generates these alongside the XML
    const match = xmlPath.match(/\/([^\/]+)\.babulus\.xml$/);
    if (match) {
      // Gatsby dev server serves the root static/public folder. The generated audio is in public/videoml/
      // Since we are running the gatsby dev server, public files are available at the root URL
      setAudioSrc(`/videoml/${match[1]}.wav`);
    }
  }, [xmlPath]);

  // Sync audio play state
  useEffect(() => {
    if (audioRef.current) {
      if (isPlaying) {
        // Only set currentTime if it's drifted to avoid stuttering
        if (Math.abs(audioRef.current.currentTime - currentTime) > 0.2) {
          audioRef.current.currentTime = currentTime;
        }
        audioRef.current.play().catch(e => console.warn("Audio playback prevented:", e));
      } else {
        audioRef.current.pause();
      }
    }
  }, [isPlaying]);

  useEffect(() => {
    // Determine the actual path.
    // The player expects the content from the root or a static directory.
    // We fetch it from the raw content path or static depending on how it's served.
    // For Gatsby static files, it's typically just /content/... if placed in static/content/
    // Let's assume xmlPath is relative to the site root
    fetch("/" + xmlPath)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load VML file: " + res.statusText);
        return res.text();
      })
      .then((text) => setXmlContent(text))
      .catch((err) => setError(err.message));
  }, [xmlPath]);

  // Try to parse duration from XML attributes
  useEffect(() => {
    if (xmlContent) {
      const match = xmlContent.match(/<vml[^>]*duration="([^"]+)"/);
      if (match && match[1]) {
        const dur = parseFloat(match[1]);
        if (!isNaN(dur)) {
          setDuration(dur);
        }
      } else {
        // sum of scene durations? 
        const sceneMatches = Array.from(xmlContent.matchAll(/<scene[^>]*duration="([^"s]+)s"/g));
        if (sceneMatches.length > 0) {
          const totalDur = sceneMatches.reduce((acc, match) => acc + parseFloat(match[1]), 0);
          if (!isNaN(totalDur)) setDuration(totalDur);
        }
      }
    }
  }, [xmlContent]);

  if (error) {
    return <div className="text-red-500 p-4">Error: {error}</div>;
  }

  if (!xmlContent || !VideomlDomPlayerComponent) {
    return <div className="text-muted p-4 flex flex-col items-center justify-center h-full min-h-[300px]">
      <div className="w-8 h-8 border-4 border-t-blue-500 border-r-transparent border-b-blue-500 border-l-transparent rounded-full animate-spin mb-4"></div>
      Loading preview...
    </div>;
  }

  // The actual player should hopefully be able to render now
  return (
    <div className="relative w-full h-full flex flex-col bg-black">
      <div className="flex-1 relative overflow-hidden">
        {audioSrc && <audio ref={audioRef} src={audioSrc} preload="auto" />}
        <VideomlDomPlayerComponent
          xml={xmlContent}
          autoPlay={isPlaying}
          clockMode="bounded"
          loop={true}
          onTimeUpdate={(time: number) => setCurrentTime(time)}
        />
      </div>

      {/* Controls */}
      <div className="h-16 bg-neutral-900 border-t border-neutral-800 flex items-center px-4 gap-4 z-20">
        <button
          onClick={() => setIsPlaying(!isPlaying)}
          className="w-10 h-10 flex items-center justify-center bg-card rounded-full text-foreground hover:bg-neutral-700"
        >
          {isPlaying ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 4h4v16H6zm8 0h4v16h-4z" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="ml-1">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
        <div className="flex-1 flex items-center gap-4">
          <span className="text-xs text-neutral-400 font-mono w-12 text-right">
            {currentTime.toFixed(1)}s
          </span>
          <div className="flex-1 h-2 bg-neutral-700 rounded-full relative overflow-hidden">
            <div 
              className="absolute top-0 left-0 h-full bg-blue-500" 
              style={{ width: `${(currentTime / duration) * 100}%` }}
            />
          </div>
          <span className="text-xs text-neutral-400 font-mono w-12">
            {duration.toFixed(1)}s
          </span>
        </div>
      </div>
    </div>
  );
}
