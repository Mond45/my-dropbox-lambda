import os
import boto3
import argon2

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
USER_TABLE_NAME = os.environ["USER_TABLE_NAME"]
SESSION_TABLE_NAME = os.environ["SESSION_TABLE_NAME"]

user_table = dynamodb.Table(USER_TABLE_NAME)
session_table = dynamodb.Table(SESSION_TABLE_NAME)

password_hasher = argon2.PasswordHasher(memory_cost=12288, time_cost=3, parallelism=1)
