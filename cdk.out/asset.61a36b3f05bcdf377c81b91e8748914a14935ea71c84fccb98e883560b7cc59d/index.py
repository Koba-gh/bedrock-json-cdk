import json
import os
import boto3
import uuid
import logging
import base64
from io import BytesIO

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
BEDROCK_MODEL_ID = os.environ['BEDROCK_MODEL_ID']

def handler(event, context):
    """
    Lambda function handler that processes PC specs PNG files from S3,
    sends them to Bedrock for extraction using Converse API, and stores the results in DynamoDB.
    """
    try:
        # Get the S3 bucket and key from the event
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        
        logger.info(f"Processing PNG file {key} from bucket {bucket}")
        
        # Get the file content from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_content = response['Body'].read()
        
        # Convert PNG to base64
        base64_image = base64.b64encode(file_content).decode('utf-8')
        
        # Call Bedrock Converse API to extract PC specs
        pc_specs = call_bedrock_converse(base64_image)
        
        # Store the extracted data in DynamoDB
        store_in_dynamodb(pc_specs)
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully processed PC specs from PNG')
        }
    
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise e

def call_bedrock_converse(base64_image):
    """
    Calls Bedrock Converse API with the PNG image and returns the extracted PC specs.
    """
    try:
        # Create the messages for the Converse API
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_image
                        }
                    },
                    {
                        "type": "text",
                        "text": """
                        Extract the following PC specifications from this image and format them as JSON:
                        - name of pc
                        - name of cpu
                        - amount of RAM (in GB)
                        - amount of storage (in GB)
                        - resolution of monitor (like 1920x1080)
                        - size of monitor (in inches)
                        
                        Return ONLY a valid JSON object with these fields. If a field is not found, use null for its value.
                        """
                    }
                ]
            }
        ]
        
        # Define the tools
        tools = [
            {
                "name": "json_tool",
                "description": "Generate a JSON object with PC specifications",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the PC"},
                        "cpu": {"type": "string", "description": "Name of the CPU"},
                        "ram": {"type": "number", "description": "Amount of RAM in GB"},
                        "storage": {"type": "number", "description": "Amount of storage in GB"},
                        "resolution": {"type": "string", "description": "Resolution of monitor (like 1920x1080)"},
                        "monitor_size": {"type": "number", "description": "Size of monitor in inches"}
                    },
                    "required": ["name", "cpu", "ram", "storage", "resolution", "monitor_size"]
                }
            }
        ]
        
        # Call the Converse API through bedrock-runtime
        response = bedrock_runtime.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            tools=tools,
            toolChoice={"name": "json_tool"},
            anthropicVersion="bedrock-2023-05-31",
            maxTokens=1000
        )
        
        # Extract the JSON tool response
        tool_response = None
        for message in response.get('messages', []):
            if message.get('role') == 'assistant' and message.get('content') is None:
                for tool_call in message.get('toolCalls', []):
                    if tool_call.get('name') == 'json_tool':
                        tool_response = json.loads(tool_call.get('input', '{}'))
        
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
        if not pc_specs.get('name'):
            pc_specs['name'] = f"pc-{uuid.uuid4()}"
        
        # Store the item in DynamoDB
        table.put_item(Item=pc_specs)
        
        logger.info(f"Successfully stored PC specs in DynamoDB: {pc_specs['name']}")
    
    except Exception as e:
        logger.error(f"Error storing in DynamoDB: {str(e)}")
        raise e
