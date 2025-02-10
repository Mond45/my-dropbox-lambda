import base64
import os

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.event_handler.api_gateway import Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.parser import parse
from aws_lambda_powertools.utilities.typing import LambdaContext

from models import FileUploadBody

app = APIGatewayRestResolver()
logger = Logger()

s3_client = boto3.client("s3")
dynamo_client = boto3.client("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]


@app.get("/hello")
def hello():
    return {"message": "hello world"}


@app.get("/file")
def get_file():
    key = app.current_event.query_string_parameters["key"]
    response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
    body = response["Body"]
    return Response(200, body=body.read())


@app.put("/file")
def upload_file():
    body = parse(app.current_event.json_body, FileUploadBody)
    s3_client.put_object(
        Bucket=BUCKET_NAME, Key=body.key, Body=base64.b64decode(body.content)
    )
    return {"message": "file uploaded"}


@app.get("/files")
def list_files():
    prefix = app.current_event.query_string_parameters.get("prefix", "")
    paginator = s3_client.get_paginator("list_objects_v2")
    result = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        result.extend(
            [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "modified": obj["LastModified"].isoformat(),
                }
                for obj in page["Contents"]
            ]
        )
    return result


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
