#!/usr/bin/env python3
import os
from aws_cdk import App

from bedrock_json_cdk.bedrock_json_stack import BedrockJsonStack

app = App()
BedrockJsonStack(app, "BedrockJsonStack")

app.synth()
