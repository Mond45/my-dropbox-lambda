# The Infrastructure

The AWS resources are defined in the `index.ts` file using Pulumi. This includes the S3 bucket, the DynamoDB tables for users and sessions, the IAM role allowing Lambda functions to access the bucket and tables, the Lambda function, and the API Gateway.

The Lambda function code is packaged using Docker builder, ensuring the dependencies are correctly handled and are compatible with the AWS environment.

To deploy the infrastructure, install [Pulumi](https://www.pulumi.com/docs/iac/download-install/) and [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). [Login to AWS](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) through the CLI, then run `pulumi up -y`.

# Code Structure

- `index.ts` contains the Pulumi code responsible for infrastructure deployment.
- `function` directory contains the code for the Lambda function
  - `function/src/lambda.py` contains the handler for the Lambda function. It defines API endpoints using [AWS Lambda Powertools](https://docs.powertools.aws.dev/lambda/python/latest/).
  - `function/src/lib.py` contains reusable functions for session tokens generation, username retrieval from a session token, and session token retrieval from request headers.
  - `function/src/resources.py` defines the resources used by the Lambda function, namely the S3 bucket, DynamoDB tables, and Argon2 password hasher object.
  - `function/src/models.py` defines the Pydantic models for request validation.

# The API

| Endpoint             | Description                                     | Request Format                                                                                                                                              | Response Format                                                                                                                                             |
| -------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **POST** `/register` | Register a new user                             | JSON Body: `{username: str, password: str}`                                                                                                                 | -                                                                                                                                                           |
| **POST** `/login`    | Login to an existing user                       | JSON Body: `{username: str, password: str}`                                                                                                                 | JSON: `{token: str}`                                                                                                                                        |
| **POST** `/logout`   | Logout                                          | HTTP Header `x-session-token`                                                                                                                               | -                                                                                                                                                           |
| **PUT** `/file`      | Upload a file                                   | HTTP Header `x-session-token`, JSON Body: `{file_name: str, content: str}` where `content` is Base64 encoded file content                                   | -                                                                                                                                                           |
| **GET** `/file`      | Download a file                                 | HTTP Header `x-session-token`, Query Param: `file_name` specifying the the filename to download, and optional `username` specifying file's owner            | Base64 encoded file content                                                                                                                                 |
| **GET** `/files`     | List files owned or shared with the active user | HTTP Header `x-session-token`                                                                                                                               | JSON: `{key: str, size: int, modified: str}` where `key` is S3 object key, `size` is file size in bytes, and `modified` is file modified date in ISO format |
| **POST** `/share`    | Share a file to a user                          | HTTP Header `x-session-token`, JSON Body: `{file_name: str, username: str}` where `file_name` is the file to share and `username` is the user to share with | -                                                                                                                                                           |
