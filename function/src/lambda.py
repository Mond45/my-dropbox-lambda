import base64
import os

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.event_handler import exceptions as HTTPErrors
from aws_lambda_powertools.event_handler.api_gateway import Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.parser import ValidationError, parse
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel


# Pydantic model for file upload request validation
class FileUploadModel(BaseModel):
    file_name: str
    content: str


BUCKET_NAME = os.environ["BUCKET_NAME"]

s3_client = boto3.client("s3")
app = APIGatewayRestResolver()
logger = Logger()


@app.put("/file")
def upload_file():
    try:
        body = parse(app.current_event.json_body, FileUploadModel)
        # file content is passed as Base64 encoded string
        file_name, content = body.file_name, body.content

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=file_name,
            Body=base64.b64decode(content),
        )
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")


@app.get("/file")
def get_file():
    try:
        file_name = app.current_event.query_string_parameters["file_name"]

        res = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_name)
        return Response(200, body=res["Body"].read())
    except KeyError:
        raise HTTPErrors.BadRequestError("Missing query parameter")
    except s3_client.exceptions.NoSuchKey:
        raise HTTPErrors.NotFoundError()


@app.get("/files")
def list_files():
    # use paginator as list_objects_v2 only returns up to 1000 objects per requests
    paginator = s3_client.get_paginator("list_objects_v2")
    result = []
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        result.extend(
            [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "modified": obj["LastModified"].isoformat(),
                }
                for obj in page.get("Contents", [])
            ]
        )
    return result


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
