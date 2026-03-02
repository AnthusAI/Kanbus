# Kanbus Public Website Scaffold

Base Gatsby 5 + Tailwind CSS project that mirrors the structure of
`../VideoML/videoml-org` and is ready to deploy on AWS Amplify Gen 2.

## Quick start

```bash
cd apps/kanb.us
npm install
npm run dev
```

Visit `http://localhost:8000` to preview the placeholder site. The home page
lists the follow-up tasks captured in Beads epic `tskl-0lb`.

## Video previews

Kanbus supports two explicit video preview modes:

1. Local-first preview (recommended while iterating):
   - Render and copy videos locally:
     - `node scripts/render-videos.js`
   - Run the site with local static assets:
     - `npm run dev:videos:local`
   - This resolves video URLs to `/videos/*` from `apps/kanb.us/static/videos`.

2. Production parity preview:
   - `npm run dev:videos:prod`
   - This resolves video URLs to:
     - `https://dmhqusv90xmye.cloudfront.net/kanbus-feature-videos/*`

Production publish is gated and requires local verification plus an explicit
confirmation:

```bash
scripts/publish-production-videos.sh --confirm-local-preview
```

## Deployment

1. Connect AWS Amplify Gen 2 to this repository and select the `apps/kanb.us`
   subdirectory.
2. Use the default build settings for Gatsby:

   ```yaml
   build:
     commands:
       - npm install
       - npm run build
   artifacts:
     baseDirectory: public
     files:
       - "**/*"
   ```

3. After the Amplify preview succeeds, continue with the DNS + domain tasks:
   - Create a Route 53 hosted zone for `kanb.us`.
   - Update GoDaddy name servers to point at Route 53.
   - Connect the custom domain to the Amplify app and request SSL.
