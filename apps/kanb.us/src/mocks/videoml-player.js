// Minimal stub for @videoml/player/react so Gatsby/Amplify builds succeed
// even when the real VideoML packages are not available.
const React = require("react");

function VideomlDomPlayer() {
  return React.createElement("div", {
    style: {
      width: "100%",
      padding: "1rem",
      background: "#0b1a2a",
      color: "#cfe0ff",
      borderRadius: "8px",
      textAlign: "center"
    }
  }, "Video preview unavailable in this build environment.");
}

module.exports = { VideomlDomPlayer };
