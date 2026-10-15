import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
export default {
  cacheDir: path.join(root, ".vite"),
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: { "@kanbus/ui": path.join(root, "dist") }
  }
};
