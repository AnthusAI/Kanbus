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

  if (stage === "build-html" || stage === "develop-html" || stage === "build-javascript") {
    config.resolve.alias = {
      "@radix-ui/react-scroll-area": path.resolve(__dirname, "src/mocks/empty-module.js"),
      "@radix-ui/react-tabs": path.resolve(__dirname, "src/mocks/empty-module.js"),
      "@videoml/player/react": path.resolve(__dirname, "src/mocks/empty-module.js"),
      "@videoml/stdlib/dom": path.resolve(__dirname, "src/mocks/empty-module.js"),
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

  if (process.env.NODE_ENV === "development") {
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

exports.onCreateDevServer = ({ app }) => {
  const repoRoot = path.resolve(__dirname, "../..");
  const vmlContentDir = path.join(repoRoot, "videos", "content");
  const previewWavDir = path.join(__dirname, "static", "videoml");

  app.get("/__vml/content/:file", (req, res) => {
    const requested = req.params.file || "";
    if (!requested.endsWith(".babulus.xml")) {
      res.status(400).json({ ok: false, error: "invalid-file-extension" });
      return;
    }

    const resolved = path.resolve(vmlContentDir, requested);
    if (!resolved.startsWith(vmlContentDir + path.sep)) {
      res.status(400).json({ ok: false, error: "invalid-path" });
      return;
    }

    if (!fs.existsSync(resolved)) {
      res.status(404).json({ ok: false, error: "xml-not-found", path: resolved });
      return;
    }

    res.setHeader("Content-Type", "application/xml; charset=utf-8");
    res.send(fs.readFileSync(resolved, "utf8"));
  });

  app.get("/__vml/health/:videoId", (req, res) => {
    const videoId = req.params.videoId || "";
    if (!/^[a-z0-9-]+$/.test(videoId)) {
      res.status(400).json({ ok: false, error: "invalid-video-id" });
      return;
    }

    const xmlPath = path.resolve(vmlContentDir, `${videoId}.babulus.xml`);
    const wavPath = path.resolve(previewWavDir, `${videoId}.wav`);
    const xmlExists = fs.existsSync(xmlPath);
    const wavExists = fs.existsSync(wavPath);
    const xmlMtimeMs = xmlExists ? fs.statSync(xmlPath).mtimeMs : null;
    const wavMtimeMs = wavExists ? fs.statSync(wavPath).mtimeMs : null;

    res.json({
      ok: xmlExists && wavExists,
      videoId,
      xmlPath,
      xmlExists,
      xmlMtimeMs,
      wavPath,
      wavExists,
      wavMtimeMs,
    });
  });
};
