"""Kanbus cloud foundation CDK stack."""

from pathlib import Path

from constructs import Construct

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_efs as efs,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_event_sources,
    aws_secretsmanager as secretsmanager,
    aws_sqs as sqs,
    aws_cloudwatch as cloudwatch,
    aws_dynamodb as dynamodb,
    aws_iot as iot,
    custom_resources as cr,
)


class KanbusCloudFoundationStack(Stack):
    """Provision core AWS resources for cloud-hosted Kanbus console services."""

    def __init__(self, scope: Construct, construct_id: str, *, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[3]
        image_dockerfile = "rust/console_lambda.Dockerfile"

        vpc = ec2.Vpc(
            self,
            "CloudVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="app",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        lambda_sg = ec2.SecurityGroup(
            self,
            "ConsoleLambdaSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for console lambda containers",
        )

        efs_sg = ec2.SecurityGroup(
            self,
            "EfsSecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Security group for Kanbus EFS",
        )
        efs_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(2049),
            description="Allow NFS from console lambda",
        )

        filesystem = efs.FileSystem(
            self,
            "KanbusTenantFilesystem",
            vpc=vpc,
            security_group=efs_sg,
            encrypted=True,
            lifecycle_policy=efs.LifecyclePolicy.AFTER_14_DAYS,
            throughput_mode=efs.ThroughputMode.BURSTING,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            removal_policy=RemovalPolicy.RETAIN,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        tenant_access_point = efs.AccessPoint(
            self,
            "TenantAccessPoint",
            file_system=filesystem,
            path="/tenants",
            create_acl=efs.Acl(owner_gid="1000", owner_uid="1000", permissions="750"),
            posix_user=efs.PosixUser(gid="1000", uid="1000"),
        )

        console_lambda = lambda_.DockerImageFunction(
            self,
            "ConsoleLambda",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=str(project_root),
                file=image_dockerfile,
                exclude=[
                    ".beads",
                    ".claude",
                    ".git",
                    ".github",
                    ".pytest_cache",
                    ".vscode",
                    "amplify",
                    "apps/kanb.us",
                    "apps/vscode",
                    "artifacts",
                    "config",
                    "custom_assets",
                    "docs",
                    "examples",
                    "features",
                    "cdk.out",
                    "**/cdk.out",
                    "**/cdk.out/**",
                    "infra/cloud/cdk.out",
                    "infra/cloud/cdk.out/**",
                    "infra/github-rulesets",
                    "node_modules",
                    "apps/console/node_modules",
                    "apps/kanb.us/node_modules",
                    "packages/ui/node_modules",
                    "rust/target",
                    "coverage-*",
                    "tmp",
                ],
            ),
            architecture=lambda_.Architecture.X86_64,
            memory_size=1024,
            timeout=Duration.seconds(120),
            tracing=lambda_.Tracing.ACTIVE,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            filesystem=lambda_.FileSystem.from_efs_access_point(tenant_access_point, "/mnt/data"),
            environment={
                "KANBUS_CLOUD_ENV": env_name,
                "KANBUS_API_STAGE": env_name,
                "CONSOLE_ASSETS_ROOT": "/opt/apps/console/dist",
            },
            description="Kanbus console API + SSE fallback runtime",
        )
        console_lambda_version = console_lambda.current_version
        console_lambda_alias = lambda_.Alias(
            self,
            "ConsoleLambdaLiveAlias",
            alias_name=env_name,
            version=console_lambda_version,
            provisioned_concurrent_executions=1 if env_name == "dev" else None,
            description="Stable versioned alias for the console Lambda runtime",
        )

        api = apigw.RestApi(
            self,
            "ConsoleApi",
            rest_api_name=f"kanbus-console-{env_name}",
            description="Kanbus console API (read APIs + SSE fallback)",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy_options=apigw.StageOptions(
                stage_name=env_name,
                metrics_enabled=True,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
            cloud_watch_role=True,
        )
        console_base_url = (
            f"https://{api.rest_api_id}.execute-api.{self.region}.{self.url_suffix}/{env_name}/"
        )

        user_pool = cognito.UserPool(
            self,
            "ConsoleUserPool",
            user_pool_name=f"kanbus-console-{env_name}-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )

        user_pool_client = user_pool.add_client(
            "ConsoleUserPoolClient",
            user_pool_client_name=f"kanbus-console-{env_name}-web",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[console_base_url],
                logout_urls=[console_base_url],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ],
        )

        user_pool_domain = user_pool.add_domain(
            "ConsoleUserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"kanbus-console-{env_name}-{self.account}"
            ),
        )

        admin_group = cognito.CfnUserPoolGroup(
            self,
            "ConsoleAdminGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="kanbus-admin",
            description="Admins allowed to manage cloud MQTT API tokens",
        )

        api_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "ConsoleApiAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name=f"kanbus-console-{env_name}-authorizer",
            identity_source="method.request.header.Authorization",
        )

        lambda_integration = apigw.LambdaIntegration(console_lambda_alias, proxy=True)
        api.root.add_method(
            "ANY",
            lambda_integration,
            authorization_type=apigw.AuthorizationType.NONE,
        )
        api.root.add_resource("{proxy+}").add_method(
            "ANY",
            lambda_integration,
            authorization_type=apigw.AuthorizationType.NONE,
        )
        api_root_resource = api.root.add_resource("api")
        api_auth_resource = api_root_resource.add_resource("auth")
        api_auth_resource.add_resource("bootstrap").add_method(
            "GET",
            lambda_integration,
            authorization_type=apigw.AuthorizationType.NONE,
        )

        identity_pool = cognito.CfnIdentityPool(
            self,
            "ConsoleIdentityPool",
            identity_pool_name=f"kanbus-console-{env_name}-identity",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=user_pool_client.user_pool_client_id,
                    provider_name=user_pool.user_pool_provider_name,
                )
            ],
        )

        authenticated_role = iam.Role(
            self,
            "ConsoleAuthenticatedRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                {
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref,
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated",
                    },
                },
                "sts:AssumeRoleWithWebIdentity",
            ),
            description="Authenticated browser role for Kanbus cloud console",
        )

        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["execute-api:Invoke"],
                resources=[api.arn_for_execute_api("*", "/*", "*")],
            )
        )
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iot:Connect"],
                resources=[
                    f"arn:{self.partition}:iot:{self.region}:{self.account}:client/*"
                ],
            )
        )
        authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iot:Subscribe", "iot:Receive"],
                resources=[
                    f"arn:{self.partition}:iot:{self.region}:{self.account}:topicfilter/"
                    "projects/*/*/events",
                    f"arn:{self.partition}:iot:{self.region}:{self.account}:topic/"
                    "projects/*/*/events",
                ],
            )
        )

        identity_pool_role_attachment = cognito.CfnIdentityPoolRoleAttachment(
            self,
            "ConsoleIdentityPoolRoleAttachment",
            identity_pool_id=identity_pool.ref,
            roles={"authenticated": authenticated_role.role_arn},
        )

        sync_dlq = sqs.Queue(
            self,
            "SyncDlq",
            queue_name=f"kanbus-sync-dlq-{env_name}",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        sync_queue = sqs.Queue(
            self,
            "SyncQueue",
            queue_name=f"kanbus-sync-{env_name}",
            visibility_timeout=Duration.minutes(5),
            retention_period=Duration.days(4),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(queue=sync_dlq, max_receive_count=5),
        )

        webhook_secret = secretsmanager.Secret(
            self,
            "GithubWebhookSecret",
            secret_name=f"kanbus/github-webhook/{env_name}",
            description="GitHub webhook secret for Kanbus sync ingress",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=40,
            ),
        )

        webhook_handler = lambda_.Function(
            self,
            "GithubWebhookIngress",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="webhook_handler.handler",
            code=lambda_.Code.from_asset(str(project_root / "infra" / "cloud" / "lambda")),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SYNC_QUEUE_URL": sync_queue.queue_url,
                "GITHUB_WEBHOOK_SECRET_ARN": webhook_secret.secret_arn,
            },
            description="Ingest GitHub push webhooks and enqueue tenant sync jobs",
        )
        sync_queue.grant_send_messages(webhook_handler)
        webhook_secret.grant_read(webhook_handler)

        sync_worker = lambda_.DockerImageFunction(
            self,
            "TenantSyncWorker",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=str(project_root / "infra" / "cloud" / "lambda"),
                file="sync_worker.Dockerfile",
            ),
            architecture=lambda_.Architecture.X86_64,
            timeout=Duration.minutes(3),
            memory_size=1024,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            filesystem=lambda_.FileSystem.from_efs_access_point(tenant_access_point, "/mnt/data"),
            environment={
                "KANBUS_TENANT_MOUNT": "/mnt/data",
            },
            description="Process tenant sync jobs and publish IoT cloud sync events",
        )
        sync_worker.add_event_source(
            lambda_event_sources.SqsEventSource(sync_queue, batch_size=5)
        )
        sync_queue.grant_consume_messages(sync_worker)
        sync_worker.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iot:Publish"],
                resources=[
                    f"arn:{self.partition}:iot:{self.region}:{self.account}:topic/projects/*/*/events"
                ],
            )
        )

        token_table = dynamodb.Table(
            self,
            "MqttApiTokenTable",
            partition_key=dynamodb.Attribute(
                name="token_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        token_pepper_secret = secretsmanager.Secret(
            self,
            "MqttApiTokenPepper",
            secret_name=f"kanbus/mqtt-token-pepper/{env_name}",
            description="Pepper used for hashing Kanbus MQTT API token secrets",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=40,
            ),
        )

        token_admin = lambda_.Function(
            self,
            "TokenAdminApi",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="token_admin.handler",
            code=lambda_.Code.from_asset(str(project_root / "infra" / "cloud" / "lambda")),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "KANBUS_TOKEN_TABLE": token_table.table_name,
                "KANBUS_TOKEN_PEPPER_SECRET_ARN": token_pepper_secret.secret_arn,
                "KANBUS_ADMIN_GROUP": "kanbus-admin",
            },
            description="Admin API for creating/listing/revoking MQTT API tokens",
        )
        token_admin.node.add_dependency(admin_group)
        token_table.grant_read_write_data(token_admin)
        token_pepper_secret.grant_read(token_admin)

        mqtt_authorizer_handler = lambda_.Function(
            self,
            "MqttTokenAuthorizerHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="mqtt_authorizer.handler",
            code=lambda_.Code.from_asset(str(project_root / "infra" / "cloud" / "lambda")),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "KANBUS_TOKEN_TABLE": token_table.table_name,
                "KANBUS_TOKEN_PEPPER_SECRET_ARN": token_pepper_secret.secret_arn,
                "KANBUS_AWS_ACCOUNT": self.account,
                "KANBUS_AWS_REGION": self.region,
                "KANBUS_COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "KANBUS_TENANT_ACCOUNT_CLAIM_KEY": "custom:account",
                "KANBUS_TENANT_PROJECT_CLAIM_KEY": "custom:project",
            },
            description="AWS IoT custom authorizer for Kanbus MQTT API tokens",
        )
        token_table.grant_read_data(mqtt_authorizer_handler)
        token_pepper_secret.grant_read(mqtt_authorizer_handler)
        mqtt_authorizer_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:GetUser"],
                resources=[user_pool.user_pool_arn],
            )
        )

        mqtt_token_authorizer = iot.CfnAuthorizer(
            self,
            "MqttTokenAuthorizer",
            authorizer_name=f"kanbus-mqtt-token-{env_name}",
            authorizer_function_arn=mqtt_authorizer_handler.function_arn,
            signing_disabled=True,
            status="ACTIVE",
            enable_caching_for_http=False,
        )

        lambda_.CfnPermission(
            self,
            "MqttTokenAuthorizerInvokePermission",
            action="lambda:InvokeFunction",
            function_name=mqtt_authorizer_handler.function_name,
            principal="iot.amazonaws.com",
            source_arn=(
                f"arn:{self.partition}:iot:{self.region}:{self.account}:authorizer/"
                f"{mqtt_token_authorizer.authorizer_name}"
            ),
        )

        tokens_resource = api_root_resource.add_resource("tokens")
        token_admin_integration = apigw.LambdaIntegration(token_admin, proxy=True)
        tokens_resource.add_method(
            "GET",
            token_admin_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=api_authorizer,
        )
        tokens_resource.add_method(
            "POST",
            token_admin_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=api_authorizer,
        )
        token_revoke_resource = tokens_resource.add_resource("{token_id}").add_resource("revoke")
        token_revoke_resource.add_method(
            "POST",
            token_admin_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=api_authorizer,
        )

        internal = api.root.add_resource("internal")
        webhooks = internal.add_resource("webhooks")
        github = webhooks.add_resource("github")
        github.add_method(
            "POST",
            apigw.LambdaIntegration(webhook_handler, proxy=True),
            authorization_type=apigw.AuthorizationType.NONE,
        )

        dlq_alarm = cloudwatch.Alarm(
            self,
            "SyncDlqVisibleMessagesAlarm",
            alarm_name=f"kanbus-sync-dlq-visible-{env_name}",
            alarm_description="Kanbus tenant sync DLQ has pending messages",
            metric=sync_dlq.metric_approximate_number_of_messages_visible(
                period=Duration.minutes(5)
            ),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        dlq_alarm.node.add_dependency(sync_dlq)

        sync_queue_age_alarm = cloudwatch.Alarm(
            self,
            "SyncQueueOldestMessageAgeAlarm",
            alarm_name=f"kanbus-sync-queue-age-{env_name}",
            alarm_description="Kanbus sync queue oldest message age is elevated",
            metric=sync_queue.metric_approximate_age_of_oldest_message(
                period=Duration.minutes(5)
            ),
            threshold=300,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
        sync_queue_age_alarm.node.add_dependency(sync_queue)

        console_lambda_errors_alarm = cloudwatch.Alarm(
            self,
            "ConsoleLambdaErrorsAlarm",
            alarm_name=f"kanbus-console-lambda-errors-{env_name}",
            alarm_description="Kanbus console lambda is reporting errors",
            metric=console_lambda_alias.metric_errors(period=Duration.minutes(5)),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        webhook_lambda_errors_alarm = cloudwatch.Alarm(
            self,
            "WebhookLambdaErrorsAlarm",
            alarm_name=f"kanbus-webhook-lambda-errors-{env_name}",
            alarm_description="Kanbus webhook ingress lambda is reporting errors",
            metric=webhook_handler.metric_errors(period=Duration.minutes(5)),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        sync_worker_errors_alarm = cloudwatch.Alarm(
            self,
            "SyncWorkerLambdaErrorsAlarm",
            alarm_name=f"kanbus-sync-worker-errors-{env_name}",
            alarm_description="Kanbus tenant sync worker lambda is reporting errors",
            metric=sync_worker.metric_errors(period=Duration.minutes(5)),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        token_admin_errors_alarm = cloudwatch.Alarm(
            self,
            "TokenAdminLambdaErrorsAlarm",
            alarm_name=f"kanbus-token-admin-errors-{env_name}",
            alarm_description="Kanbus token admin API lambda is reporting errors",
            metric=token_admin.metric_errors(period=Duration.minutes(5)),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        mqtt_authorizer_errors_alarm = cloudwatch.Alarm(
            self,
            "MqttAuthorizerLambdaErrorsAlarm",
            alarm_name=f"kanbus-mqtt-authorizer-errors-{env_name}",
            alarm_description="Kanbus MQTT token authorizer lambda is reporting errors",
            metric=mqtt_authorizer_handler.metric_errors(period=Duration.minutes(5)),
            threshold=0,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        api_client_errors_alarm = cloudwatch.Alarm(
            self,
            "ApiGateway4xxAlarm",
            alarm_name=f"kanbus-console-api-4xx-{env_name}",
            alarm_description="Kanbus console API is returning elevated 4XX responses",
            metric=api.metric_client_error(period=Duration.minutes(5)),
            threshold=20,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )

        iot_endpoint = cr.AwsCustomResource(
            self,
            "IotDataEndpoint",
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Iot",
                action="describeEndpoint",
                parameters={"endpointType": "iot:Data-ATS"},
                physical_resource_id=cr.PhysicalResourceId.of("iot-data-ats-endpoint"),
            ),
            on_update=cr.AwsSdkCall(
                service="Iot",
                action="describeEndpoint",
                parameters={"endpointType": "iot:Data-ATS"},
                physical_resource_id=cr.PhysicalResourceId.of("iot-data-ats-endpoint"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["iot:DescribeEndpoint"],
                        resources=["*"],
                    )
                ]
            ),
        )
        iot_endpoint.node.add_dependency(identity_pool_role_attachment)
        console_lambda.add_environment("KANBUS_AUTH_MODE", "cognito_pkce")
        console_lambda.add_environment("KANBUS_COGNITO_CLIENT_ID", user_pool_client.user_pool_client_id)
        console_lambda.add_environment("KANBUS_COGNITO_DOMAIN_URL", user_pool_domain.base_url())
        console_lambda.add_environment("KANBUS_COGNITO_REDIRECT_URI", console_base_url)
        console_lambda.add_environment("KANBUS_COGNITO_LOGOUT_URI", console_base_url)
        console_lambda.add_environment("KANBUS_COGNITO_ISSUER", user_pool.user_pool_provider_url)
        console_lambda.add_environment("KANBUS_IDENTITY_POOL_ID", identity_pool.ref)
        console_lambda.add_environment("KANBUS_TENANT_ACCOUNT_CLAIM_KEY", "custom:account")
        console_lambda.add_environment("KANBUS_TENANT_PROJECT_CLAIM_KEY", "custom:project")
        console_lambda.add_environment(
            "KANBUS_IOT_DATA_ENDPOINT", iot_endpoint.get_response_field("endpointAddress")
        )
        console_lambda.add_environment(
            "KANBUS_MQTT_CUSTOM_AUTHORIZER_NAME", mqtt_token_authorizer.authorizer_name
        )
        sync_worker.add_environment(
            "KANBUS_IOT_DATA_ENDPOINT", iot_endpoint.get_response_field("endpointAddress")
        )

        CfnOutput(self, "ApiBaseUrl", value=api.url, description="Regional API base URL")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "UserPoolHostedUiBaseUrl", value=user_pool_domain.base_url())
        CfnOutput(
            self,
            "UserPoolIssuerUrl",
            value=user_pool.user_pool_provider_url,
            description="JWT issuer URL used by Cognito authorizer",
        )
        CfnOutput(self, "IdentityPoolId", value=identity_pool.ref)
        CfnOutput(self, "MqttTokenAuthorizerName", value=mqtt_token_authorizer.authorizer_name)
        CfnOutput(self, "MqttTokenTableName", value=token_table.table_name)
        CfnOutput(
            self,
            "IotDataEndpointAddress",
            value=iot_endpoint.get_response_field("endpointAddress"),
            description="AWS IoT Core data endpoint",
        )
        CfnOutput(self, "SyncQueueUrl", value=sync_queue.queue_url)
        CfnOutput(self, "SyncQueueArn", value=sync_queue.queue_arn)
        CfnOutput(self, "SyncDlqArn", value=sync_dlq.queue_arn)
        CfnOutput(self, "GithubWebhookSecretArn", value=webhook_secret.secret_arn)
        CfnOutput(self, "TenantEfsFileSystemId", value=filesystem.file_system_id)
        CfnOutput(self, "TenantEfsAccessPointId", value=tenant_access_point.access_point_id)
        CfnOutput(self, "TenantEfsMountPath", value="/mnt/data")
        CfnOutput(
            self,
            "TenantRootTemplate",
            value="/mnt/data/{account}/{project}",
            description="Tenant root path template expected by console_lambda",
        )
