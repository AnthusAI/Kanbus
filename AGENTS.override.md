# Agent Overrides

## Environment

Use the py311 conda environment for Python tooling. Prefer:

```bash
conda run -n py311 <command>
```

## Shell

If a command fails in your default shell, retry it using zsh.

## AWS Deployment

The Amplify Gen 2 backend (S3 video bucket + CloudFront CDN) must be deployed
to the **`anthus`** AWS profile:

```bash
AWS_PROFILE=anthus npx ampx sandbox   # dev
AWS_PROFILE=anthus npx ampx deploy    # production
```

Video uploads also use the `anthus` profile:

```bash
AWS_PROFILE=anthus VIDEOS_BUCKET=<bucket-name> VIDEOS_PREFIX=videos node scripts/upload-videos.js
```
