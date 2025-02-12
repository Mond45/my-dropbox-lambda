import base64
from datetime import datetime, timedelta
import re

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.event_handler.api_gateway import Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.parser import parse, ValidationError
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.event_handler import exceptions as HTTPErrors
from boto3.dynamodb.conditions import Attr

from lib import generate_token, get_active_username, get_session_token
from models import UserFileModel, FileUploadModel, UserModel
from resources import s3_client, user_table, session_table, password_hasher, BUCKET_NAME

app = APIGatewayRestResolver()
logger = Logger()


@app.post("/register")
def register():
    try:
        body = parse(app.current_event.json_body, UserModel)
        username, password = body.username, body.password

        if re.fullmatch(r"[a-zA-Z0-9_\-]+", username) is None:
            raise HTTPErrors.BadRequestError("Invalid username")

        hashed_password = password_hasher.hash(password)
        user_table.put_item(
            Item={"Username": username, "Password": hashed_password, "SharedFiles": []},
            ConditionExpression=Attr("Username").not_exists(),
        )
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")
    except user_table.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPErrors.BadRequestError("Username already exists")


@app.post("/login")
def login():
    try:
        body = parse(app.current_event.json_body, UserModel)
        username, password = body.username, body.password

        user = user_table.get_item(Key={"Username": username})
        password_hasher.verify(user["Item"]["Password"], password)

        token = generate_token()
        session_table.put_item(
            Item={"Token": token, "Username": username},
            ConditionExpression=Attr("Token").not_exists(),
        )

        return {"token": token}
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")
    except:
        raise HTTPErrors.UnauthorizedError("Invalid credentials")


@app.post("/logout")
def logout():
    token = get_session_token(app)
    session_table.delete_item(Key={"Token": token})


@app.put("/file")
def upload_file():
    try:
        body = parse(app.current_event.json_body, FileUploadModel)
        file_name, content = body.file_name, body.content

        token = get_session_token(app)
        active_username = get_active_username(token)

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=f"{active_username}/{file_name}",
            Body=base64.b64decode(content),
        )
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")


@app.get("/file")
def get_file():
    try:
        token = get_session_token(app)
        active_username = get_active_username(token)

        username = app.current_event.query_string_parameters.get("username", None)
        file_name = app.current_event.query_string_parameters["file_name"]

        key = f"{username or active_username}/{file_name}"
        if username is not None and username != active_username:
            user = user_table.get_item(Key={"Username": active_username})
            if key not in user["Item"]["SharedFiles"]:
                raise HTTPErrors.NotFoundError()

        res = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        return Response(200, body=res["Body"].read())

    except KeyError:
        raise HTTPErrors.BadRequestError("Missing query parameter")
    except s3_client.exceptions.NoSuchKey:
        raise HTTPErrors.NotFoundError()


@app.get("/files")
def list_files():
    token = get_session_token(app)
    active_username = get_active_username(token)

    # Get all files owned by the active user
    paginator = s3_client.get_paginator("list_objects_v2")
    result = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=f"{active_username}/"):
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

    # Get all files shared with the active user
    user = user_table.get_item(Key={"Username": active_username})
    shared_files: list[str] = user["Item"]["SharedFiles"]
    for file in shared_files:
        head = s3_client.head_object(Bucket=BUCKET_NAME, Key=file)
        result.append(
            {
                "key": file,
                "size": head["ContentLength"],
                "modified": head["LastModified"].isoformat(),
            }
        )

    return result


@app.post("/share")
def share_file():
    try:
        token = get_session_token(app)
        active_username = get_active_username(token)

        body = parse(app.current_event.json_body, UserFileModel)
        file_name, target_username = body.file_name, body.username

        if target_username == active_username:
            raise HTTPErrors.BadRequestError("Already owner of the file")

        key = f"{active_username}/{file_name}"
        # ensure file existence
        s3_client.head_object(Bucket=BUCKET_NAME, Key=key)

        user_table.update_item(
            Key={"Username": target_username},
            UpdateExpression="SET SharedFiles = list_append(SharedFiles, :i)",
            ExpressionAttributeValues={":i": [key]},
            ConditionExpression=Attr("Username").exists()
            & (~Attr("SharedFiles").contains(key)),
        )
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")
    except s3_client.exceptions.NoSuchKey:
        raise HTTPErrors.NotFoundError()
    except user_table.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPErrors.BadRequestError("User not found or file already shared")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
