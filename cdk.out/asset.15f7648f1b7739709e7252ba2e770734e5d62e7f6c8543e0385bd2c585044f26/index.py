import json
import os
import boto3
import uuid
import logging

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
    ".pdf": "pdf",
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
            "body": json.dumps(
                f"Successfully processed PC specs from {file_format} file"
            ),
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
            content_list.append(
                {"image": {"format": file_format, "source": {"bytes": file_content}}}
            )
        elif file_format == "pdf":
            # For PDF files - Claude doesn't directly support PDF in Converse API
            # Convert to base64 and include as a reference
            content_list.append(
                {
                    "document": {
                        "format": "pdf",
                        "name": "filename",
                        "source": {"bytes": file_content},
                    }
                }
            )
        elif file_format == "text":
            # For text files, decode the content
            text_content = file_content.decode("utf-8")
            content_list.append({"text": text_content})

        # Add the instruction text
        content_list.append(
            {
                "text": """
            Extract the following PC specifications and format them as JSON:
            - name of pc
            - name of cpu
            - amount of RAM (in GB)
            - amount of storage (in GB)
            - resolution width (in pixels)
            - resolution height (in pixels)
            - size of monitor (in inches)
            - price (in yen)
            
            Return ONLY a valid JSON object with these fields. If a field is not found or cannot be determined, 
            use an empty string for string fields and 0 for numeric fields.
            """,
            }
        )

        # Create the messages for the Converse API
        messages = [
            {
                "role": "user",
                "content": content_list,
            }
        ]

        # Define the tools with updated schema to include price and separate resolution
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
                                    "resolution_width": {
                                        "type": "number",
                                        "description": "Width of monitor resolution in pixels",
                                    },
                                    "resolution_height": {
                                        "type": "number",
                                        "description": "Height of monitor resolution in pixels",
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
                                    "resolution_width",
                                    "resolution_height",
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

        # Ensure all fields have default values if missing
        defaults = {
            "name": "",
            "cpu": "",
            "ram": 0,
            "storage": 0,
            "resolution_width": 0,
            "resolution_height": 0,
            "monitor_size": 0,
            "price": 0,
        }

        # Apply defaults for any missing fields and preserve decimal values
        for key, default_value in defaults.items():
            if key not in tool_response or tool_response[key] is None:
                tool_response[key] = default_value
            elif isinstance(default_value, (int, float)):
                # Ensure numeric values are properly typed but preserve decimals
                try:
                    tool_response[key] = float(tool_response[key])
                except (ValueError, TypeError):
                    tool_response[key] = default_value

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

        # Add a timestamp and unique ID if name is missing or empty
        if not pc_specs.get("name"):
            pc_specs["name"] = f"pc-{uuid.uuid4()}"

        # Store the item in DynamoDB
        table.put_item(Item=pc_specs)

        logger.info(f"Successfully stored PC specs in DynamoDB: {pc_specs['name']}")

    except Exception as e:
        logger.error(f"Error storing in DynamoDB: {str(e)}")
        raise e
