const path = require("path");
const fs = require("fs");

exports.onCreateWebpackConfig = ({ actions, stage }) => {
  const config = {
    resolve: {
      modules: [path.resolve(__dirname, "node_modules")]
    }
  };

  if (stage === "develop" || stage === "develop-html") {
    config.watchOptions = {
      ignored: ["**/public/**", "**/.cache/**"]
    };
  }

  if (stage === "build-html" || stage === "develop-html") {
    config.resolve.alias = {
      "@radix-ui/react-scroll-area": path.resolve(__dirname, "src/mocks/empty-module.js"),
      "@radix-ui/react-tabs": path.resolve(__dirname, "src/mocks/empty-module.js"),
      gsap: path.resolve(__dirname, "src/mocks/empty-module.js")
    };
  }

  actions.setWebpackConfig(config);
};

function suppressVirtualModuleLoop() {
  try {
    const reduxPath = require.resolve("gatsby/dist/redux", {
      paths: [__dirname],
    });
    const redux = require(reduxPath);
    const emitter = redux.emitter;
    if (!emitter || typeof emitter.emit !== "function") return;
    const originalEmit = emitter.emit.bind(emitter);
    emitter.emit = (eventName, payload) => {
      if (eventName === "SOURCE_FILE_CHANGED" && payload != null) {
        const pathStr =
          typeof payload === "string"
            ? payload
            : payload?.file ?? payload?.payload?.file;
        if (
          pathStr &&
          (String(pathStr).includes(".cache") ||
            String(pathStr).includes("_this_is_virtual_fs_path_"))
        ) {
          return;
        }
      }
      return originalEmit(eventName, payload);
    };
  } catch {
    // ignore if resolve or patch fails
  }
}

exports.onPreInit = () => {
  suppressVirtualModuleLoop();

  if (process.env.GATSBY_VIDEOS_BASE_URL) {
    return;
  }

  const outputsPath = path.resolve(__dirname, "../../amplify_outputs.json");
  if (!fs.existsSync(outputsPath)) {
    return;
  }

  try {
    const outputs = JSON.parse(fs.readFileSync(outputsPath, "utf8"));
    const cdnUrl = outputs?.custom?.videosCdnUrl;
    if (cdnUrl) {
      process.env.GATSBY_VIDEOS_BASE_URL = cdnUrl;
    }
  } catch {
    // amplify_outputs.json present but unreadable — fall through
  }
};
