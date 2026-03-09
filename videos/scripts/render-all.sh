#!/bin/bash
set -e
SCRIPTS_ROOT=..
OUT=out
BABULUS_BUNDLE=node_modules/babulus/public/babulus-standard.js
export PATH="$(pwd)/node_modules/.bin:$PATH"

echo "=== Rebuilding browser-components bundle ==="
npm run bundle:components

render_video() {
  local id=$1
  echo "=== Rendering $id ==="
  vml render \
    --script "$SCRIPTS_ROOT/src/videos/$id/$id.script.json" \
    --timeline "$SCRIPTS_ROOT/src/videos/$id/$id.timeline.json" \
    --audio "$SCRIPTS_ROOT/public/videoml/$id.wav" \
    --frames "$OUT/frames/$id" \
    --out "$OUT/$id.mp4" \
    --browser-bundle "$BABULUS_BUNDLE" \
    --browser-bundle public/browser-components.js
  echo "=== Done $id, cleaning frames ==="
  rm -rf "$OUT/frames/$id"
}

render_video intro
render_video core-management
render_video jira-sync
render_video local-tasks
render_video beads-compatibility
render_video virtual-projects
render_video vscode-plugin
render_video policy-as-code
render_video lifecycle-hooks
render_video realtime-collaboration

echo "=== All renders complete ==="
