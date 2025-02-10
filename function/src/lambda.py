import os
from time import time
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools import Logger
import boto3

app = APIGatewayRestResolver()
logger = Logger()

s3_client = boto3.client("s3")
dynamo_client = boto3.client("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]


@app.get("/hello")
def hello():
    return {"message": "hello world"}


@app.put("/file")
def upload_file():
    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=f"{int(time())}.txt", Body="Hello, world!"
    )
    return {"message": "file uploaded"}


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
