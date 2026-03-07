export default {
  paths: ["../../features/console/**/*.feature"],
  import: ["tests/support/**/*.js", "tests/steps/**/*.js"],
  tags: "not @cli",
  format: ["progress"],
  publishQuiet: true
};
