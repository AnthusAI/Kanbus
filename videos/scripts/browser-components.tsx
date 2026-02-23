import { IntroScene } from "../src/components/IntroScene";

const { registerComponent } = (window as any).Babulus;

if (!registerComponent) {
  throw new Error("Babulus standard bundle must be loaded first (window.Babulus.registerComponent not found)");
}

registerComponent("IntroScene", IntroScene);

console.log("[Kanbus] Custom components registered:", (window as any).Babulus.listComponents());
