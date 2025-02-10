import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";
import * as apigateway from "@pulumi/aws-apigateway";
import * as dockerBuild from "@pulumi/docker-build";
import * as command from "@pulumi/command";

export = async () => {
  const s3Bucket = new aws.s3.BucketV2("mydropbox-bucket");

  const userTable = new aws.dynamodb.Table("mydropbox-user-table", {
    attributes: [{ name: "Username", type: "S" }],
    hashKey: "Username",
    billingMode: "PAY_PER_REQUEST",
  });

  const lambdaRole = new aws.iam.Role("mydropbox-lambda-role", {
    assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal(
      aws.iam.Principals.LambdaPrincipal
    ),
    managedPolicyArns: [aws.iam.ManagedPolicy.AWSLambdaBasicExecutionRole],
  });

  new aws.iam.RolePolicy("mydropbox-lambda-s3-policy", {
    role: lambdaRole,
    policy: s3Bucket.arn.apply((arn) =>
      JSON.stringify({
        Version: "2012-10-17",
        Statement: [
          {
            Action: "s3:*",
            Resource: [`${arn}`, `${arn}/*`],
            Effect: "Allow",
          },
        ],
      })
    ),
  });

  new aws.iam.RolePolicy("mydropbox-lambda-dynamo-policy", {
    role: lambdaRole,
    policy: userTable.arn.apply((arn) =>
      JSON.stringify({
        Version: "2012-10-17",
        Statement: [
          {
            Action: "dynamodb:*",
            Resource: [`${arn}`, `${arn}/*`],
            Effect: "Allow",
          },
        ],
      })
    ),
  });

  await command.local.run({
    command: "uv export --no-hashes -o requirements.txt",
    dir: "./function",
  });

  const buildLambda = new dockerBuild.Image("mydropbox-lambda-build", {
    push: false,
    context: { location: "./function" },
    dockerfile: { location: "./function/Dockerfile" },
    exports: [
      {
        local: { dest: "./dist" },
      },
    ],
  });

  const fn = new aws.lambda.Function(
    "mydropbox-function",
    {
      role: lambdaRole.arn,
      runtime: aws.lambda.Runtime.Python3d13,
      handler: "lambda.lambda_handler",
      code: new pulumi.asset.AssetArchive({
        ".": new pulumi.asset.FileArchive("./dist/"),
      }),
      environment: {
        variables: {
          BUCKET_NAME: s3Bucket.bucket,
          TABLE_NAME: userTable.name,
        },
      },
    },
    { dependsOn: [buildLambda] }
  );

  const api = new apigateway.RestAPI("api", {
    routes: [
      { path: "/hello", method: "GET", eventHandler: fn },
      { path: "/file", method: "PUT", eventHandler: fn },
    ],
  });

  return {
    url: api.url,
  };
};
