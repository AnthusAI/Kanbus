import { IntroScene } from "../src/components/IntroScene";
import { CodeUiSyncVideo } from "../src/components/CodeUiSyncVideo";
import { AnimatedPictogramVideo } from "../src/components/AnimatedPictogramVideo";
import { CliDemoVideo } from "../src/components/CliDemoVideo";
import { JiraSyncDemoVideo } from "../src/components/JiraSyncDemoVideo";
import { LocalTasksDemoVideo } from "../src/components/LocalTasksDemoVideo";
import { BeadsDemoVideo } from "../src/components/BeadsDemoVideo";
import { VirtualProjectsDemoVideo } from "../src/components/VirtualProjectsDemoVideo";
import { VsCodeDemoVideo } from "../src/components/VsCodeDemoVideo";
import { PolicyDemoVideo } from "../src/components/PolicyDemoVideo";
import { TextBlock } from "../src/components/TextBlock";
// For the CLI renderer, window might be mocked, but we need to ensure Babulus exists
if (typeof window !== "undefined") {
  // Inject Kanbus CSS variables into the headless browser environment so
  // MP4 exports are styled nicely (defaulting to Dark Mode for the videos).
  // Skip injection when the site's CSS already provides the tokens (e.g., on
  // the marketing site where commons.css is loaded).
  if (typeof document !== "undefined" && !document.getElementById("kanbus-tokens")) {
    const alreadyDefined = getComputedStyle(document.documentElement)
      .getPropertyValue("--background").trim();
    if (!alreadyDefined) {
      const style = document.createElement("style");
      style.id = "kanbus-tokens";
      style.textContent = `
        :root {
          --font-sans: "Inter", "SF Pro Text", "Helvetica Neue", "Arial", sans-serif;
          --font-serif: "Source Serif 4", "Iowan Old Style", "Times New Roman", serif;
          --font-mono: "IBM Plex Mono", "SFMono-Regular", "Menlo", "Monaco", "Consolas", monospace;
          --font-body: var(--font-sans);

          /* Console dark */
          --background: #0f1115;
          --card: #14171d;
          --card-muted: #1e222b;
          --card-outline: #262c36;
          --frame: #0f1115;
          --column: #1a1f28;
          --text-foreground: #e7e9ee;
          --text-muted: #9ca3af;
          --text-selected: #7dd3fc;
          --border: #262c36;
          --shadow-card: none;

          --danger-bg: #451a1d;
          --danger-text: #fca5a5;

          --glow-center: rgba(0, 0, 0, 0.5);
          --glow-edge: rgba(0, 0, 0, 0);
        }
      `;
      document.head.appendChild(style);
    }
  }

  if (!(window as any).Babulus) {
    (window as any).Babulus = {
      components: new Map(),
      registerComponent: (name: string, Component: any) => {
        (window as any).Babulus.components.set(name, Component);
      },
      listComponents: () => Array.from((window as any).Babulus.components.keys()),
      getComponent: (name: string) => (window as any).Babulus.components.get(name)
    };
  }

  const registerComponent = (window as any).Babulus?.registerComponent;

  if (registerComponent) {
    registerComponent("IntroScene", IntroScene);
    registerComponent("CodeUiSyncVideo", CodeUiSyncVideo);
    registerComponent("AnimatedPictogramVideo", AnimatedPictogramVideo);
    registerComponent("CliDemoVideo", CliDemoVideo);
    registerComponent("JiraSyncDemoVideo", JiraSyncDemoVideo);
    registerComponent("LocalTasksDemoVideo", LocalTasksDemoVideo);
    registerComponent("BeadsDemoVideo", BeadsDemoVideo);
    registerComponent("VirtualProjectsDemoVideo", VirtualProjectsDemoVideo);
    registerComponent("VsCodeDemoVideo", VsCodeDemoVideo);
    registerComponent("PolicyDemoVideo", PolicyDemoVideo);
    registerComponent("TextBlock", TextBlock);

    console.log("[Kanbus] Custom components registered:", (window as any).Babulus.listComponents());
  }

  // Define renderFrame on window for the renderer to call
  if (!(window as any).renderFrame) {
    (window as any).renderFrame = async function(options: any) {
      if ((window as any).Babulus && (window as any).Babulus._updateFrame) {
        await (window as any).Babulus._updateFrame(options.frame, options.config.fps);
      }
    };
  }
}
