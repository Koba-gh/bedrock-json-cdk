import json
import os
import boto3
import uuid
import logging

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
    Lambda function handler that processes PC specs files from S3,
    sends them to Bedrock for extraction, and stores the results in DynamoDB.
    """
    try:
        # Get the S3 bucket and key from the event
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        
        logger.info(f"Processing file {key} from bucket {bucket}")
        
        # Get the file content from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_content = response['Body'].read().decode('utf-8')
        
        # Create prompt for Bedrock
        prompt = create_bedrock_prompt(file_content)
        
        # Call Bedrock to extract PC specs
        pc_specs = call_bedrock(prompt)
        
        # Store the extracted data in DynamoDB
        store_in_dynamodb(pc_specs)
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully processed PC specs')
        }
    
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise e

def create_bedrock_prompt(file_content):
    """
    Creates a prompt for Bedrock to extract PC specifications from the file content.
    """
    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": f"""
                Extract the following PC specifications from the text below and format them as JSON:
                - name of pc
                - name of cpu
                - amount of RAM (in GB)
                - amount of storage (in GB)
                - resolution of monitor (like 1920x1080)
                - size of monitor (in inches)
                
                Here's the text to analyze:
                {file_content}
                
                Return ONLY a valid JSON object with these fields. If a field is not found, use null for its value.
                """
            }
        ],
        "tools": [
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
        ],
        "tool_choice": {"name": "json_tool"}
    }
    
    return prompt

def call_bedrock(prompt):
    """
    Calls Bedrock with the given prompt and returns the extracted PC specs.
    """
    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(prompt)
        )
        
        response_body = json.loads(response['body'].read().decode())
        
        # Extract the JSON tool response
        tool_response = None
        for message in response_body.get('messages', []):
            if message.get('role') == 'assistant' and message.get('content') is None:
                for tool_call in message.get('tool_calls', []):
                    if tool_call.get('name') == 'json_tool':
                        tool_response = tool_call.get('input', {})
        
        if not tool_response:
            logger.error("Failed to extract PC specs from Bedrock response")
            raise Exception("Failed to extract PC specs from Bedrock response")
        
        return tool_response
    
    except Exception as e:
        logger.error(f"Error calling Bedrock: {str(e)}")
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
