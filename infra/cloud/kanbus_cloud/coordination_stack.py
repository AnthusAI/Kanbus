"""Disposable AWS resources for remote coordination integration tests."""

from pathlib import Path

from constructs import Construct

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_iot as iot,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
    custom_resources as cr,
)


class KanbusCoordinationIntegrationStack(Stack):
    """Small, disposable Cognito/API/DynamoDB/IoT environment for coordination tests."""

    def __init__(self, scope: Construct, construct_id: str, *, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[3]
        lambda_directory = str(project_root / "infra" / "cloud" / "lambda")

        api = apigw.RestApi(
            self,
            "CoordinationApi",
            rest_api_name=f"kanbus-coordination-it-{env_name}",
            description="Disposable Kanbus coordination integration API",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy_options=apigw.StageOptions(stage_name=env_name),
            cloud_watch_role=False,
        )
        api_root = api.root.add_resource("api")

        user_pool = cognito.UserPool(
            self,
            "CoordinationUserPool",
            user_pool_name=f"kanbus-coordination-it-{env_name}-users",
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
            custom_attributes={
                "account": cognito.StringAttribute(mutable=False, min_len=1, max_len=128),
                "project": cognito.StringAttribute(mutable=False, min_len=1, max_len=128),
            },
            removal_policy=RemovalPolicy.DESTROY,
        )
        user_pool_client = user_pool.add_client(
            "CoordinationUserPoolClient",
            user_pool_client_name=f"kanbus-coordination-it-{env_name}-client",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
        )
        admin_group = cognito.CfnUserPoolGroup(
            self,
            "CoordinationAdminGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="kanbus-admin",
            description="Admins allowed to manage disposable MQTT API tokens",
        )
        api_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "CoordinationApiAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name=f"kanbus-coordination-it-{env_name}-authorizer",
            identity_source="method.request.header.Authorization",
        )

        lease_table = dynamodb.Table(
            self,
            "CoordinationLeaseTable",
            table_name=f"kanbus-coordination-it-leases-{env_name}",
            partition_key=dynamodb.Attribute(
                name="tenant_key", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="resource_key", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            point_in_time_recovery=False,
            removal_policy=RemovalPolicy.DESTROY,
        )
        _add_lease_routes(
            self,
            api=api,
            api_root=api_root,
            authorizer=api_authorizer,
            table=lease_table,
        )

        token_table = dynamodb.Table(
            self,
            "MqttApiTokenTable",
            table_name=f"kanbus-coordination-it-mqtt-tokens-{env_name}",
            partition_key=dynamodb.Attribute(
                name="token_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=False,
            removal_policy=RemovalPolicy.DESTROY,
        )
        token_pepper = secretsmanager.Secret(
            self,
            "MqttApiTokenPepper",
            secret_name=f"kanbus/coordination-it/mqtt-token-pepper/{env_name}",
            description="Generated pepper for disposable Kanbus MQTT token tests",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=40,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )
        token_admin = lambda_.Function(
            self,
            "TokenAdminApi",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="token_admin.handler",
            code=lambda_.Code.from_asset(lambda_directory),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "KANBUS_TOKEN_TABLE": token_table.table_name,
                "KANBUS_TOKEN_PEPPER_SECRET_ARN": token_pepper.secret_arn,
                "KANBUS_ADMIN_GROUP": "kanbus-admin",
            },
            description="Create, list, and revoke disposable MQTT API tokens",
        )
        token_admin.node.add_dependency(admin_group)
        token_table.grant_read_write_data(token_admin)
        token_pepper.grant_read(token_admin)

        mqtt_authorizer_handler = lambda_.Function(
            self,
            "MqttTokenAuthorizerHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="mqtt_authorizer.handler",
            code=lambda_.Code.from_asset(lambda_directory),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "KANBUS_TOKEN_TABLE": token_table.table_name,
                "KANBUS_TOKEN_PEPPER_SECRET_ARN": token_pepper.secret_arn,
                "KANBUS_AWS_ACCOUNT": self.account,
                "KANBUS_AWS_REGION": self.region,
                "KANBUS_COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "KANBUS_TENANT_ACCOUNT_CLAIM_KEY": "custom:account",
                "KANBUS_TENANT_PROJECT_CLAIM_KEY": "custom:project",
            },
            description="AWS IoT custom authorizer for disposable MQTT API tokens",
        )
        token_table.grant_read_data(mqtt_authorizer_handler)
        token_pepper.grant_read(mqtt_authorizer_handler)
        mqtt_authorizer_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:GetUser"],
                resources=[user_pool.user_pool_arn],
            )
        )
        mqtt_authorizer = iot.CfnAuthorizer(
            self,
            "MqttTokenAuthorizer",
            authorizer_name=f"kanbus-mqtt-coordination-it-{env_name}",
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
                f"{mqtt_authorizer.authorizer_name}"
            ),
        )

        tokens_resource = api_root.add_resource("tokens")
        token_admin_integration = apigw.LambdaIntegration(token_admin, proxy=True)
        for method in ("GET", "POST"):
            tokens_resource.add_method(
                method,
                token_admin_integration,
                authorization_type=apigw.AuthorizationType.COGNITO,
                authorizer=api_authorizer,
            )
        tokens_resource.add_resource("{token_id}").add_resource("revoke").add_method(
            "POST",
            token_admin_integration,
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=api_authorizer,
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
                [iam.PolicyStatement(actions=["iot:DescribeEndpoint"], resources=["*"])]
            ),
        )

        CfnOutput(
            self,
            "CoordinationLeaseApiBaseUrl",
            value=api.url,
            description=(
                "REST API stage base URL; append /api/coordination/leases/{resource}"
            ),
        )
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(
            self,
            "UserPoolIssuerUrl",
            value=user_pool.user_pool_provider_url,
        )
        CfnOutput(
            self,
            "IotDataEndpointAddress",
            value=iot_endpoint.get_response_field("endpointAddress"),
        )
        CfnOutput(self, "MqttTokenAuthorizerName", value=mqtt_authorizer.authorizer_name)
        CfnOutput(self, "MqttTokenTableName", value=token_table.table_name)
        CfnOutput(self, "CoordinationLeaseTableName", value=lease_table.table_name)


def _add_lease_routes(
    stack: Stack,
    *,
    api: apigw.RestApi,
    api_root: apigw.IResource,
    authorizer: apigw.IAuthorizer,
    table: dynamodb.ITable,
) -> None:
    """Add the hard lease API using API Gateway's direct DynamoDB service integration."""
    role = iam.Role(
        stack,
        "CoordinationLeaseApiRole",
        assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        description="API Gateway role limited to disposable coordination lease rows",
    )
    role.add_to_policy(
        iam.PolicyStatement(
            actions=["dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:UpdateItem"],
            resources=[table.table_arn],
        )
    )
    resource = api_root.add_resource("coordination").add_resource("leases").add_resource(
        "{resource}"
    )
    resource.add_cors_preflight(
        allow_origins=apigw.Cors.ALL_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    validator = api.add_request_validator(
        "CoordinationLeaseRequestValidator",
        request_validator_name="kanbus-coordination-it-lease-validator",
        validate_request_body=True,
        validate_request_parameters=True,
    )

    def string_schema() -> apigw.JsonSchema:
        return apigw.JsonSchema(
            type=apigw.JsonSchemaType.STRING, min_length=1, max_length=256
        )

    acquire_model = api.add_model(
        "CoordinationLeaseAcquireRequest",
        model_name="CoordinationLeaseAcquireRequest",
        content_type="application/json",
        schema=apigw.JsonSchema(
            type=apigw.JsonSchemaType.OBJECT,
            required=["owner", "claim_id", "revision", "ttl_seconds"],
            additional_properties=False,
            properties={
                "owner": string_schema(),
                "claim_id": string_schema(),
                "revision": apigw.JsonSchema(type=apigw.JsonSchemaType.INTEGER, minimum=1),
                "ttl_seconds": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.NUMBER,
                    exclusive_minimum=True,
                    minimum=0,
                    maximum=86400,
                ),
            },
        ),
    )
    renew_model = api.add_model(
        "CoordinationLeaseRenewRequest",
        model_name="CoordinationLeaseRenewRequest",
        content_type="application/json",
        schema=apigw.JsonSchema(
            type=apigw.JsonSchemaType.OBJECT,
            required=["owner", "claim_id", "extend_seconds"],
            additional_properties=False,
            properties={
                "owner": string_schema(),
                "claim_id": string_schema(),
                "extend_seconds": apigw.JsonSchema(
                    type=apigw.JsonSchemaType.NUMBER,
                    exclusive_minimum=True,
                    minimum=0,
                    maximum=86400,
                ),
            },
        ),
    )
    release_model = api.add_model(
        "CoordinationLeaseReleaseRequest",
        model_name="CoordinationLeaseReleaseRequest",
        content_type="application/json",
        schema=apigw.JsonSchema(
            type=apigw.JsonSchemaType.OBJECT,
            required=["owner", "claim_id"],
            additional_properties=False,
            properties={"owner": string_schema(), "claim_id": string_schema()},
        ),
    )

    def scope_template() -> str:
        # If claims are absent, deliberately emit no DynamoDB operation fields. DynamoDB
        # rejects that malformed request before reading or writing any table item; the
        # integration response below maps this exact guard path to a stable 403.
        return '''#set($account = $context.authorizer.claims.get('custom:account'))
#set($project = $context.authorizer.claims.get('custom:project'))
#if(!$account || $account == '' || !$project || $project == '')
  {"InvalidTenantScope":true}
#else
#set($tenantKey = "ACCOUNT#$util.base64Encode($account)#PROJECT#$util.base64Encode($project)")
#set($resourceName = $util.urlDecode($input.params('resource')))
#set($resourceKey = "RESOURCE#$util.base64Encode($resourceName)")'''

    def escaped(expression: str) -> str:
        return f"$util.escapeJavaScript({expression})" + r""".replaceAll("\\'", "'")"""

    def item_response(path: str) -> str:
        return "\n".join(
            [
                f"#set($item = $input.path('{path}'))",
                "{",
                f'  "resource": "{escaped("$item.resource.S")}",',
                f'  "owner": "{escaped("$item.owner.S")}",',
                f'  "claim_id": "{escaped("$item.claim_id.S")}",',
                '  "revision": $item.revision.N,',
                '  "claimed_at": $item.claimed_at.N,',
                '  "expires_at": $item.expires_at.N',
                "}",
            ]
        )

    def conditional_failure() -> str:
        return '''#if(!$context.authorizer.claims.get('custom:account') || $context.authorizer.claims.get('custom:account') == '' || !$context.authorizer.claims.get('custom:project') || $context.authorizer.claims.get('custom:project') == '')
  #set($context.responseOverride.status = 403)
  {"error":"tenant scope missing"}
#else
#set($failureType = $input.path('$.__type'))
#if($failureType.contains('ConditionalCheckFailedException'))
  #set($item = $input.path('$.Item'))
  #set($now = $context.requestTimeEpoch / 1000)
  #if(!$item || $item.isEmpty() || !$item.expires_at)
    #set($context.responseOverride.status = 404)
    {"error":"no live lease"}
  #else
    #set($expiresAt = $util.parseJson($item.expires_at.N))
    #if($expiresAt <= $now)
      #set($context.responseOverride.status = 404)
      {"error":"no live lease"}
    #else
      #set($context.responseOverride.status = 403)
      {"error":"lease owner mismatch"}
    #end
  #end
#else
  #set($context.responseOverride.status = 500)
  {"error":"coordination lease request failed"}
#end
#end'''

    def request_template(operation: str) -> str:
        scope = scope_template()
        key = (
            '"Key":{"tenant_key":{"S":"$tenantKey"},'
            '"resource_key":{"S":"$resourceKey"}}'
        )
        table_name = table.table_name
        body = [scope, "#set($now = $context.requestTimeEpoch / 1000)"]
        if operation == "acquire":
            body.extend(
                [
                    "#set($expiresAt = $now + $input.path('$.ttl_seconds'))",
                    "{",
                    f'  "TableName":"{table_name}",',
                    f"  {key},",
                    '  "UpdateExpression":"SET #account = :account, #project = :project, #resource = :resource, #owner = :owner, #claim_id = :claim_id, #revision = :revision, #claimed_at = :now, #expires_at = :expires_at",',
                    '  "ConditionExpression":"attribute_not_exists(#owner) OR #expires_at <= :now",',
                    '  "ExpressionAttributeNames":{"#account":"account_id","#project":"project_id","#resource":"resource","#owner":"owner","#claim_id":"claim_id","#revision":"revision","#claimed_at":"claimed_at","#expires_at":"expires_at"},',
                    '  "ExpressionAttributeValues":{',
                    f'    ":account":{{"S":"{escaped("$account")}"}}, ":project":{{"S":"{escaped("$project")}"}},',
                    f'    ":resource":{{"S":"{escaped("$resourceName")}"}},',
                    f'    ":owner":{{"S":"{escaped("$input.path(\'$.owner\')")}"}},',
                    f'    ":claim_id":{{"S":"{escaped("$input.path(\'$.claim_id\')")}"}},',
                    '    ":revision":{"N":"$input.path(\'$.revision\')"},',
                    '    ":now":{"N":"$now"}, ":expires_at":{"N":"$expiresAt"}',
                    "  },",
                    '  "ReturnValues":"ALL_NEW",',
                    '  "ReturnValuesOnConditionCheckFailure":"ALL_OLD"',
                    "}",
                ]
            )
        elif operation == "renew":
            body.extend(
                [
                    "#set($extension = $input.path('$.extend_seconds'))",
                    "{",
                    f'  "TableName":"{table_name}",',
                    f"  {key},",
                    '  "UpdateExpression":"SET #expires_at = #expires_at + :extension",',
                    '  "ConditionExpression":"#owner = :owner AND #claim_id = :claim_id AND #expires_at > :now",',
                    '  "ExpressionAttributeNames":{"#owner":"owner","#claim_id":"claim_id","#expires_at":"expires_at"},',
                    '  "ExpressionAttributeValues":{',
                    f'    ":owner":{{"S":"{escaped("$input.path(\'$.owner\')")}"}},',
                    f'    ":claim_id":{{"S":"{escaped("$input.path(\'$.claim_id\')")}"}},',
                    '    ":now":{"N":"$now"}, ":extension":{"N":"$extension"}',
                    "  },",
                    '  "ReturnValues":"ALL_NEW",',
                    '  "ReturnValuesOnConditionCheckFailure":"ALL_OLD"',
                    "}",
                ]
            )
        elif operation == "release":
            body.extend(
                [
                    "{",
                    f'  "TableName":"{table_name}",',
                    f"  {key},",
                    '  "ConditionExpression":"#owner = :owner AND #claim_id = :claim_id AND #expires_at > :now",',
                    '  "ExpressionAttributeNames":{"#owner":"owner","#claim_id":"claim_id","#expires_at":"expires_at"},',
                    '  "ExpressionAttributeValues":{',
                    f'    ":owner":{{"S":"{escaped("$input.path(\'$.owner\')")}"}},',
                    f'    ":claim_id":{{"S":"{escaped("$input.path(\'$.claim_id\')")}"}},',
                    '    ":now":{"N":"$now"}',
                    "  },",
                    '  "ReturnValuesOnConditionCheckFailure":"ALL_OLD"',
                    "}",
                ]
            )
        else:
            body.extend(
                [
                    "{",
                    f'  "TableName":"{table_name}",',
                    f"  {key},",
                    '  "ConsistentRead":true',
                    "}",
                ]
            )
        body.append("#end")
        return "\n".join(body)

    def integration(
        operation: str, action: str, success_status: str, success_template: str
    ) -> apigw.Integration:
        if operation == "acquire":
            error_template = '''#if(!$context.authorizer.claims.get('custom:account') || $context.authorizer.claims.get('custom:account') == '' || !$context.authorizer.claims.get('custom:project') || $context.authorizer.claims.get('custom:project') == '')
  #set($context.responseOverride.status = 403)
  {"error":"tenant scope missing"}
#elseif($input.path('$.__type').contains('ConditionalCheckFailedException'))
  #set($context.responseOverride.status = 409)
  {"error":"lease already held"}
#else
  #set($context.responseOverride.status = 500)
  {"error":"coordination lease request failed"}
#end'''
        elif operation in {"renew", "release"}:
            error_template = conditional_failure()
        else:
            error_template = '''#if(!$context.authorizer.claims.get('custom:account') || $context.authorizer.claims.get('custom:account') == '' || !$context.authorizer.claims.get('custom:project') || $context.authorizer.claims.get('custom:project') == '')
  #set($context.responseOverride.status = 403)
  {"error":"tenant scope missing"}
#else
  #set($context.responseOverride.status = 500)
  {"error":"coordination lease inspect failed"}
#end'''
        return apigw.Integration(
            type=apigw.IntegrationType.AWS,
            integration_http_method="POST",
            uri=f"arn:{stack.partition}:apigateway:{stack.region}:dynamodb:action/{action}",
            options=apigw.IntegrationOptions(
                credentials_role=role,
                passthrough_behavior=apigw.PassthroughBehavior.NEVER,
                request_parameters={
                    "integration.request.header.Content-Type": "'application/x-amz-json-1.0'"
                },
                request_templates={"application/json": request_template(operation)},
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code=("409" if operation == "acquire" else "403"),
                        selection_pattern="4\\d{2}",
                        response_templates={"application/json": error_template},
                    ),
                    apigw.IntegrationResponse(
                        status_code=success_status,
                        response_templates={"application/json": success_template},
                    ),
                ],
            ),
        )

    def add_method(
        method: str,
        operation: str,
        action: str,
        status: str,
        response_template: str,
        model: apigw.IModel | None = None,
    ) -> None:
        response_statuses = {status, "500"}
        response_statuses.add("403")
        if operation == "acquire":
            response_statuses.add("409")
        if operation in {"renew", "release", "inspect"}:
            response_statuses.add("404")
        resource.add_method(
            method,
            integration(operation, action, status, response_template),
            authorization_type=apigw.AuthorizationType.COGNITO,
            authorizer=authorizer,
            request_parameters={"method.request.path.resource": True},
            request_models={"application/json": model} if model else None,
            request_validator=validator if model else None,
            method_responses=[
                apigw.MethodResponse(status_code=code)
                for code in sorted(response_statuses)
            ],
        )

    add_method(
        "POST",
        "acquire",
        "UpdateItem",
        "201",
        item_response("$.Attributes"),
        acquire_model,
    )
    add_method(
        "PUT",
        "renew",
        "UpdateItem",
        "200",
        item_response("$.Attributes"),
        renew_model,
    )
    add_method(
        "DELETE",
        "release",
        "DeleteItem",
        "204",
        "",
        release_model,
    )
    inspect_response = "\n".join(
        [
            "#set($item = $input.path('$.Item'))",
            "#set($now = $context.requestTimeEpoch / 1000)",
            "#if(!$item || $item.isEmpty() || !$item.expires_at)",
            '  #set($context.responseOverride.status = 404)',
            '  {"error":"no live lease"}',
            "#else",
            "  #set($expiresAt = $util.parseJson($item.expires_at.N))",
            "  #if($expiresAt <= $now)",
            '    #set($context.responseOverride.status = 404)',
            '    {"error":"no live lease"}',
            "  #else",
            *item_response("$.Item").splitlines(),
            "  #end",
            "#end",
        ]
    )
    add_method("GET", "inspect", "GetItem", "200", inspect_response)
