import base64
import os
import secrets

import argon2
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.event_handler import exceptions as HTTPErrors
from aws_lambda_powertools.event_handler.api_gateway import Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.parser import ValidationError, parse
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Attr
from pydantic import BaseModel

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
USER_TABLE_NAME = os.environ["USER_TABLE_NAME"]
SESSION_TABLE_NAME = os.environ["SESSION_TABLE_NAME"]

user_table = dynamodb.Table(USER_TABLE_NAME)
session_table = dynamodb.Table(SESSION_TABLE_NAME)

password_hasher = argon2.PasswordHasher(memory_cost=12288, time_cost=3, parallelism=1)


class FileUploadModel(BaseModel):
    file_name: str
    content: str


class UserModel(BaseModel):
    username: str
    password: str


class UserFileModel(BaseModel):
    username: str
    file_name: str


app = APIGatewayRestResolver()
logger = Logger()


def generate_token():
    return secrets.token_hex(16)


def get_active_username(token):
    try:
        res = session_table.get_item(Key={"Token": token})
        return res["Item"]["Username"]
    except:
        raise HTTPErrors.UnauthorizedError("Session not found")


def get_session_token(app):
    try:
        return app.current_event.headers["x-session-token"]
    except KeyError:
        raise HTTPErrors.UnauthorizedError("Session token not found")


@app.post("/register")
def register():
    try:
        body = parse(app.current_event.json_body, UserModel)
        username, password = body.username, body.password
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")

    hashed_password = password_hasher.hash(password)

    try:
        user_table.put_item(
            Item={"Username": username, "Password": hashed_password, "SharedFiles": []},
            ConditionExpression=Attr("Username").not_exists(),
        )
    except user_table.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPErrors.BadRequestError("Username already exists")


@app.post("/login")
def login():
    try:
        body = parse(app.current_event.json_body, UserModel)
        username, password = body.username, body.password
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")

    try:
        user = user_table.get_item(Key={"Username": username})
        password_hasher.verify(user["Item"]["Password"], password)

        token = generate_token()
        session_table.put_item(
            Item={"Token": token, "Username": username},
            ConditionExpression=Attr("Token").not_exists(),
        )

        return {"token": token}
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
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")

    token = get_session_token(app)
    active_username = get_active_username(token)

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=f"{active_username}/{file_name}",
        Body=base64.b64decode(content),
    )


@app.get("/file")
def get_file():
    token = get_session_token(app)
    active_username = get_active_username(token)

    try:
        username = app.current_event.query_string_parameters.get("username", None)
        file_name = app.current_event.query_string_parameters["file_name"]
    except KeyError:
        raise HTTPErrors.BadRequestError("Missing query parameter")

    try:
        key = f"{username or active_username}/{file_name}"
        if username is not None and username != active_username:
            user = user_table.get_item(Key={"Username": active_username})
            if key not in user["Item"]["SharedFiles"]:
                raise HTTPErrors.NotFoundError()

        res = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        return Response(200, body=res["Body"].read())
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
    token = get_session_token(app)
    active_username = get_active_username(token)

    try:
        body = parse(app.current_event.json_body, UserFileModel)
        file_name, target_username = body.file_name, body.username
    except ValidationError:
        raise HTTPErrors.BadRequestError("Invalid request body")

    if target_username == active_username:
        raise HTTPErrors.BadRequestError("Already owner of the file")

    try:
        key = f"{active_username}/{file_name}"
        # ensure file existence
        s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
    except s3_client.exceptions.NoSuchKey:
        raise HTTPErrors.NotFoundError()

    try:
        user_table.update_item(
            Key={"Username": target_username},
            UpdateExpression="SET SharedFiles = list_append(SharedFiles, :i)",
            ExpressionAttributeValues={":i": [key]},
            ConditionExpression=Attr("Username").exists()
            & (~Attr("SharedFiles").contains(key)),
        )
    except user_table.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPErrors.BadRequestError("Failed to share file")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
