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

Set `GATSBY_VIDEOS_BASE_URL` to point at a local or CDN-backed videos folder.
For local previews, you can use `GATSBY_VIDEOS_BASE_URL=/videos` and copy
rendered MP4/JPG assets into `apps/kanb.us/static/videos`.

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
