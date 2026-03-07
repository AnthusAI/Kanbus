const inCI = process.env.GITHUB_ACTIONS === "true";
const tagExpr = inCI ? "not @cli and not @skip-in-ci" : "not @cli";

export default {
  paths: ["../../features/console/**/*.feature"],
  import: ["tests/support/**/*.js", "tests/steps/**/*.js"],
  tags: tagExpr,
  format: ["progress"],
  publishQuiet: true
};
