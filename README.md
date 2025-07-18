# Bedrock JSON Extraction CDK Project

This project uses AWS CDK to deploy a serverless architecture that processes PC specification images:

1. PNG images containing PC specifications are uploaded to an S3 bucket
2. A Lambda function is triggered by the S3 upload
3. The Lambda sends the image to Amazon Bedrock (Claude 4 Sonnet) using the Converse API
4. Bedrock extracts structured data using the JSON tool
5. The extracted data is stored in DynamoDB

## Architecture

```
S3 (PNG files) -> Lambda -> Bedrock Converse API -> DynamoDB
```

## Extracted PC Specifications

The system extracts the following PC specifications from images:
- Name of PC
- Name of CPU
- Amount of RAM (in GB)
- Amount of storage (in GB)
- Resolution of monitor (like 1920x1080)
- Size of monitor (in inches)

## Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.9 or higher
- Node.js 14 or higher
- AWS CDK installed (`npm install -g aws-cdk`)

## Setup

1. Create and activate a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Build the Lambda layer with required dependencies:
   ```
   ./build_layer.sh
   ```

4. Bootstrap your AWS environment (if not already done):
   ```
   cdk bootstrap
   ```

5. Deploy the stack:
   ```
   cdk deploy
   ```

## Usage

1. Upload a PNG image containing PC specifications to the created S3 bucket
2. The Lambda function will automatically process the image
3. Extracted data will be stored in the DynamoDB table

## Example Image Content

The PNG images should contain information about PC specifications, such as:

```
PC Name: Gaming Beast X9000
CPU: Intel Core i9-13900K
Memory: 64GB DDR5
Storage: 2TB NVMe SSD
Monitor: 32-inch 4K UHD (3840x2160)
```

The image can be a screenshot, photo of a spec sheet, or any other format as long as the text is readable.

## Cleanup

To remove all resources created by this stack:

```
cdk destroy
```
