export default {
  paths: ["../../features/console/**/*.feature"],
  import: ["tests/support/**/*.js", "tests/steps/**/*.js"],
  tags: "not @cli and not @console-server",
  format: ["progress"],
  publishQuiet: true
};
