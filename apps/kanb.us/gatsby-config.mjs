import nodeCrypto from "node:crypto";
if (!globalThis.crypto) {
  globalThis.crypto = nodeCrypto.webcrypto;
}

const config = {
  siteMetadata: {
    title: "Kanbus",
    description: "Git-backed project management with dual Python and Rust implementations",
    siteUrl: "https://kanb.us",
  },
  graphqlTypegen: false,
  plugins: ["gatsby-plugin-postcss"],
};

export default config;
