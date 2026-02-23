import { defineBackend } from "@aws-amplify/backend";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import {
  AllowedMethods,
  CachePolicy,
  Distribution,
  OriginAccessIdentity,
  ResponseHeadersPolicy,
  ViewerProtocolPolicy
} from "aws-cdk-lib/aws-cloudfront";
import { S3Origin } from "aws-cdk-lib/aws-cloudfront-origins";
import {
  AccountRootPrincipal,
  CanonicalUserPrincipal,
  Effect,
  PolicyStatement
} from "aws-cdk-lib/aws-iam";
import { BlockPublicAccess, Bucket, BucketEncryption } from "aws-cdk-lib/aws-s3";

const backend = defineBackend({});

// Public marketing video hosting:
// - S3 bucket is private
// - CloudFront provides the public HTTPS URL
// This is intentionally decoupled from the Gatsby build output; the site references videos via URL.
const videosStack = backend.createStack("videos");
const videosBucket = new Bucket(videosStack, "VideosBucket", {
  encryption: BucketEncryption.S3_MANAGED,
  enforceSSL: true,
  blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
  removalPolicy: RemovalPolicy.RETAIN
});

const originAccessIdentity = new OriginAccessIdentity(videosStack, "VideosOAI");
videosBucket.addToResourcePolicy(
  new PolicyStatement({
    effect: Effect.ALLOW,
    principals: [
      new CanonicalUserPrincipal(
        originAccessIdentity.cloudFrontOriginAccessIdentityS3CanonicalUserId
      )
    ],
    actions: ["s3:GetObject"],
    resources: [videosBucket.arnForObjects("*")]
  })
);

// Allow uploads from the account root (DevOps-managed credentials).
videosBucket.addToResourcePolicy(
  new PolicyStatement({
    effect: Effect.ALLOW,
    principals: [new AccountRootPrincipal()],
    actions: ["s3:ListBucket"],
    resources: [videosBucket.bucketArn]
  })
);
videosBucket.addToResourcePolicy(
  new PolicyStatement({
    effect: Effect.ALLOW,
    principals: [new AccountRootPrincipal()],
    actions: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    resources: [videosBucket.arnForObjects("*")]
  })
);

const corsHeaders = new ResponseHeadersPolicy(
  videosStack,
  "VideosCorsHeaders",
  {
    corsBehavior: {
      accessControlAllowCredentials: false,
      accessControlAllowHeaders: ["*"],
      accessControlAllowMethods: ["GET", "HEAD", "OPTIONS"],
      accessControlAllowOrigins: ["*"],
      accessControlMaxAge: Duration.minutes(10),
      originOverride: true
    }
  }
);

const videosCdn = new Distribution(videosStack, "VideosCdn", {
  defaultBehavior: {
    origin: new S3Origin(videosBucket, { originAccessIdentity }),
    allowedMethods: AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
    viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: CachePolicy.CACHING_OPTIMIZED,
    responseHeadersPolicy: corsHeaders
  }
});

backend.addOutput({
  custom: {
    videosBucketName: videosBucket.bucketName,
    videosCdnDomain: videosCdn.domainName,
    videosCdnUrl: `https://${videosCdn.domainName}`
  }
});
