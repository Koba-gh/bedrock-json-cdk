import json
import os
import boto3
import uuid
import logging
import base64
import mimetypes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client("s3")
bedrock_runtime = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")

# Get environment variables
DYNAMODB_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

# Define supported file types
SUPPORTED_EXTENSIONS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".txt": "text",
    ".pdf": "pdf"
}


def handler(event, context):
    """
    Lambda function handler that processes PC specs files from S3,
    sends them to Bedrock for extraction using Converse API, and stores the results in DynamoDB.
    Supports PNG, JPEG, PDF, and text files.
    """
    try:
        # Get the S3 bucket and key from the event
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        
        # Determine file extension
        _, file_extension = os.path.splitext(key.lower())
        
        if file_extension not in SUPPORTED_EXTENSIONS:
            logger.error(f"Unsupported file type: {file_extension}")
            return {
                "statusCode": 400,
                "body": json.dumps(f"Unsupported file type: {file_extension}"),
            }
            
        file_format = SUPPORTED_EXTENSIONS[file_extension]
        logger.info(f"Processing {file_format} file {key} from bucket {bucket}")

        # Get the file content from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_content = response["Body"].read()

        # Call Bedrock Converse API to extract PC specs
        pc_specs = call_bedrock_converse(file_content, file_format)

        # Store the extracted data in DynamoDB
        store_in_dynamodb(pc_specs)

        return {
            "statusCode": 200,
            "body": json.dumps(f"Successfully processed PC specs from {file_format} file"),
        }

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise e


def call_bedrock_converse(file_content, file_format):
    """
    Calls Bedrock Converse API with the file content and returns the extracted PC specs.
    Supports PNG, JPEG, PDF, and text files.
    """
    try:
        # Create content based on file format
        content_list = []
        
        if file_format in ["png", "jpeg"]:
            # For image files
            content_list.append({"image": {"format": file_format, "source": {"bytes": file_content}}})
        elif file_format == "pdf":
            # For PDF files
            content_list.append({"document": {"format": "pdf", "source": {"bytes": file_content}}})
        elif file_format == "text":
            # For text files, decode the content
            text_content = file_content.decode('utf-8')
            # No need for separate content item for the instruction
            content_list.append({"text": text_content})
        
        # Add the instruction text
        content_list.append({
            "text": """
            Extract the following PC specifications and format them as JSON:
            - name of pc
            - name of cpu
            - amount of RAM (in GB)
            - amount of storage (in GB)
            - resolution of monitor (like 1920x1080)
            - size of monitor (in inches)
            - price (in yen)
            
            Return ONLY a valid JSON object with these fields. If a field is not found, use null for its value.
            """,
        })

        # Create the messages for the Converse API
        messages = [
            {
                "role": "user",
                "content": content_list,
            }
        ]

        # Define the tools with updated schema to include price
        toolConfig = {
            "tools": [
                {
                    "toolSpec": {
                        "name": "json_tool",
                        "description": "Generate a JSON object with PC specifications",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Name of the PC",
                                    },
                                    "cpu": {
                                        "type": "string",
                                        "description": "Name of the CPU",
                                    },
                                    "ram": {
                                        "type": "number",
                                        "description": "Amount of RAM in GB",
                                    },
                                    "storage": {
                                        "type": "number",
                                        "description": "Amount of storage in GB",
                                    },
                                    "resolution": {
                                        "type": "string",
                                        "description": "Resolution of monitor (like 1920x1080)",
                                    },
                                    "monitor_size": {
                                        "type": "number",
                                        "description": "Size of monitor in inches",
                                    },
                                    "price": {
                                        "type": "number",
                                        "description": "Price in Japanese yen",
                                    },
                                },
                                "required": [
                                    "name",
                                    "cpu",
                                    "ram",
                                    "storage",
                                    "resolution",
                                    "monitor_size",
                                    "price",
                                ],
                            },
                        },
                    }
                }
            ]
        }

        # Call the Converse API through bedrock-runtime
        response = bedrock_runtime.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            toolConfig=toolConfig,
        )

        # Extract the JSON tool response
        tool_response = None
        output = response["output"]["message"]
        for content in output["content"]:
            if "toolUse" in content:
                tool_response = content["toolUse"]["input"]

        if not tool_response:
            logger.error("Failed to extract PC specs from Bedrock response")
            raise Exception("Failed to extract PC specs from Bedrock response")

        return tool_response

    except Exception as e:
        logger.error(f"Error calling Bedrock Converse API: {str(e)}")
        raise e


def store_in_dynamodb(pc_specs):
    """
    Stores the extracted PC specs in DynamoDB.
    """
    try:
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)

        # Add a timestamp and unique ID if name is missing
        if not pc_specs.get("name"):
            pc_specs["name"] = f"pc-{uuid.uuid4()}"

        # Store the item in DynamoDB
        table.put_item(Item=pc_specs)

        logger.info(f"Successfully stored PC specs in DynamoDB: {pc_specs['name']}")

    except Exception as e:
        logger.error(f"Error storing in DynamoDB: {str(e)}")
        raise e
