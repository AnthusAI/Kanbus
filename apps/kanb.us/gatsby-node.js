const path = require("path");
const fs = require("fs");

exports.onCreateWebpackConfig = ({ actions, stage }) => {
  const config = {
    resolve: {
      modules: [path.resolve(__dirname, "node_modules")]
    }
  };

  if (stage === "build-html" || stage === "develop-html") {
    config.resolve.alias = {
      "@radix-ui/react-scroll-area": path.resolve(__dirname, "src/mocks/empty-module.js"),
      "@radix-ui/react-tabs": path.resolve(__dirname, "src/mocks/empty-module.js"),
      gsap: path.resolve(__dirname, "src/mocks/empty-module.js")
    };
  }

  actions.setWebpackConfig(config);
};

exports.onPreInit = () => {
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
