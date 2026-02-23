import type * as esbuild from "esbuild";
import { resolve } from "path";

export const globalsPlugin: esbuild.Plugin = {
  name: "globals",
  setup(build) {
    build.onResolve({ filter: /^react$/ }, () => {
      return { path: "react", namespace: "globals" };
    });
    build.onResolve({ filter: /^react-dom$/ }, () => {
      return { path: "react-dom", namespace: "globals" };
    });
    build.onResolve({ filter: /^react-dom\/client$/ }, () => {
      return { path: "react-dom/client", namespace: "globals" };
    });
    build.onResolve({ filter: /^remotion$/ }, () => {
      return { path: resolve(__dirname, "../src/remotion-shim.tsx") };
    });

    build.onLoad({ filter: /.*/, namespace: "globals" }, (args) => {
      if (args.path === "react") {
        return {
          contents: "module.exports = window.React",
          loader: "js"
        };
      }
      if (args.path === "react-dom") {
        return {
          contents: "module.exports = window.ReactDOM",
          loader: "js"
        };
      }
      if (args.path === "react-dom/client") {
        return {
          contents: "module.exports = window.ReactDOM",
          loader: "js"
        };
      }
      return null;
    });
  }
};
