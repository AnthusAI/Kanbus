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
import { RealtimeCollaborationDemoVideo } from "../src/components/RealtimeCollaborationDemoVideo";
import { TextBlock } from "../src/components/TextBlock";
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

          /* Console light */
          --background: #f9f9f9;
          --card: #f9f9f9;
          --card-muted: #e0e0e0;
          --card-outline: #d9d9d9;
          --frame: #f9f9f9;
          --column: #f0f0f0;
          --text-foreground: #202020;
          --text-muted: #838383;
          --text-selected: #00749e;
          --border: #d9d9d9;
          --shadow-card: none;

          --danger-bg: #fef2f2;
          --danger-text: #991b1b;

          --glow-center: rgba(255, 255, 255, 0.9);
          --glow-edge: rgba(255, 255, 255, 0);
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
    registerComponent("RealtimeCollaborationDemoVideo", RealtimeCollaborationDemoVideo);
    registerComponent("TextBlock", TextBlock);

    console.log("[Kanbus] Custom components registered:", (window as any).Babulus.listComponents());
  }

}
