from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_s3_notifications as s3n,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class BedrockJsonStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for PC specs files
        pc_specs_bucket = s3.Bucket(
            self,
            "PCSpecsFilesBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Create DynamoDB table to store processed PC specs
        pc_specs_table = dynamodb.Table(
            self,
            "PCSpecsTable",
            partition_key=dynamodb.Attribute(
                name="name", type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # Create IAM role for Lambda function
        lambda_role = iam.Role(
            self,
            "PCSpecsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # Add permissions to the Lambda role
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[
                    pc_specs_bucket.bucket_arn,
                    f"{pc_specs_bucket.bucket_arn}/*",
                ],
            )
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:PutItem", "dynamodb:UpdateItem"],
                resources=[pc_specs_table.table_arn],
            )
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock-runtime:InvokeModel",
                    "bedrock-runtime:Converse",
                ],
                resources=[
                    "*"
                ],  # You might want to restrict this to specific model ARNs
            )
        )

        # Create Lambda layer with dependencies
        lambda_layer = lambda_.LayerVersion(
            self,
            "PCSpecsLambdaLayer",
            code=lambda_.Code.from_asset("app"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Layer containing dependencies for file processing",
        )

        # Create Lambda function with increased timeout and memory for file processing
        pc_specs_lambda = lambda_.Function(
            self,
            "PCSpecsLambdaFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_asset("app"),
            layers=[lambda_layer],
            role=lambda_role,
            timeout=Duration.seconds(60),  # Increased timeout for file processing
            memory_size=512,  # Increased memory for handling files
            environment={
                "DYNAMODB_TABLE_NAME": pc_specs_table.table_name,
                "BEDROCK_MODEL_ID": "us.anthropic.claude-sonnet-4-20250514-v1:0",  # Correct model ID for Claude 3 Sonnet
            },
        )

        # Add S3 event notifications to trigger Lambda for supported file types
        # PNG files
        pc_specs_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pc_specs_lambda),
            s3.NotificationKeyFilter(suffix=".png"),
        )
        
        # JPEG files
        pc_specs_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pc_specs_lambda),
            s3.NotificationKeyFilter(suffix=".jpg"),
        )
        
        pc_specs_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pc_specs_lambda),
            s3.NotificationKeyFilter(suffix=".jpeg"),
        )
        
        # PDF files
        pc_specs_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pc_specs_lambda),
            s3.NotificationKeyFilter(suffix=".pdf"),
        )
        
        # Text files
        pc_specs_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(pc_specs_lambda),
            s3.NotificationKeyFilter(suffix=".txt"),
        )
