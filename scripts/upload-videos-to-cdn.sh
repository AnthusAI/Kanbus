#!/bin/bash
set -e

# Video upload script for Kanbus
# Uploads rendered videos to AWS S3 with AWS profile support
# Usage: ./scripts/upload-videos-to-cdn.sh [--profile PROFILE] [--dry-run]

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEOS_OUT="$REPO_ROOT/videos/out"
AWS_PROFILE="${AWS_PROFILE:-anthus}"
DRY_RUN=""
VIDEOS_BUCKET=""
VIDEOS_PREFIX="kanbus-feature-videos"

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      AWS_PROFILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="--dryrun"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Kanbus Video Upload${NC}"
echo "===================="
echo ""

# Check if videos exist
if [ ! -d "$VIDEOS_OUT" ]; then
  echo -e "${RED}Error: Videos directory not found: $VIDEOS_OUT${NC}"
  echo "Run 'node scripts/render-videos.js' first to generate videos."
  exit 1
fi

VIDEO_COUNT=$(find "$VIDEOS_OUT" -type f \( -name "*.mp4" -o -name "*.jpg" \) | wc -l)
if [ "$VIDEO_COUNT" -eq 0 ]; then
  echo -e "${RED}Error: No .mp4 or .jpg files found in $VIDEOS_OUT${NC}"
  exit 1
fi

echo "Videos to upload: $VIDEO_COUNT files"
echo "AWS Profile: $AWS_PROFILE"
echo "S3 Prefix: $VIDEOS_PREFIX"
echo ""

# Verify AWS credentials
if ! aws sts get-caller-identity --profile "$AWS_PROFILE" &>/dev/null; then
  echo -e "${RED}Error: Cannot authenticate with AWS profile '$AWS_PROFILE'${NC}"
  echo "Check your AWS configuration and try again."
  exit 1
fi

# Find the Amplify videos bucket for this profile
echo "Searching for Amplify videos bucket..."
BUCKETS=$(aws s3 ls --profile "$AWS_PROFILE" 2>/dev/null | grep -i "video" | awk '{print $3}' || true)

if [ -z "$BUCKETS" ]; then
  echo -e "${RED}Error: No S3 buckets with 'video' in the name found${NC}"
  echo "Available buckets:"
  aws s3 ls --profile "$AWS_PROFILE" 2>/dev/null | awk '{print "  " $3}' || echo "  (none)"
  exit 1
fi

# If multiple buckets, use the first one (usually the Amplify bucket)
VIDEOS_BUCKET=$(echo "$BUCKETS" | head -1)

echo -e "${GREEN}Found bucket: $VIDEOS_BUCKET${NC}"
echo ""

# Perform the upload
DESTINATION="s3://${VIDEOS_BUCKET}/${VIDEOS_PREFIX}/"

if [ -n "$DRY_RUN" ]; then
  echo -e "${YELLOW}DRY RUN: Showing what would be uploaded${NC}"
  echo ""
fi

echo "Uploading to: $DESTINATION"
echo ""

aws s3 sync \
  "$VIDEOS_OUT" \
  "$DESTINATION" \
  --profile "$AWS_PROFILE" \
  --exclude "*" \
  --include "*.mp4" \
  --include "*.jpg" \
  --cache-control "public,max-age=300" \
  $DRY_RUN

echo ""
echo -e "${GREEN}Upload complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Set environment variable for local preview:"
echo "   export GATSBY_VIDEOS_BASE_URL=https://${VIDEOS_BUCKET}.s3.amazonaws.com/${VIDEOS_PREFIX}"
echo ""
echo "2. Or use the Amplify distribution URL if available:"
echo "   export GATSBY_VIDEOS_BASE_URL=https://d1234.cloudfront.net/${VIDEOS_PREFIX}"
echo ""
echo "3. Run the web app:"
echo "   cd apps/kanb.us && npm run develop"
