# AWS Bedrock Setup Guide

This guide walks you through setting up Amazon Bedrock as an LLM provider for DeepCode.

## Prerequisites

- An AWS account with Bedrock access
- Python 3.10+ with `boto3>=1.34.0` installed (included in `requirements.txt`)
- An AWS region where Bedrock is available (e.g., `us-east-1`, `us-west-2`, `eu-west-1`)

## Step 1: Enable Bedrock Model Access

1. Sign in to the [AWS Console](https://console.aws.amazon.com/)
2. Navigate to **Amazon Bedrock** > **Model access**
3. Click **Manage model access**
4. Select the Claude models you want to use:
   - `Anthropic Claude 3.5 Sonnet` (recommended)
   - `Anthropic Claude 3 Opus`
   - `Anthropic Claude 3 Sonnet`
   - `Anthropic Claude 3 Haiku`
5. Click **Save changes** and wait for access to be granted

> Model access requests are usually approved instantly for on-demand models.

## Step 2: Configure IAM Permissions

Your AWS credentials need the following IAM policy at minimum:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListFoundationModels"
      ],
      "Resource": "*"
    }
  ]
}
```

To restrict to specific models, replace `"Resource": "*"` with:

```json
"Resource": [
  "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-*",
  "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-opus-*"
]
```

## Step 3: Configure Credentials

DeepCode resolves AWS credentials in the following priority order:

### Option A: IAM Role (Recommended for Production)

If running on EC2, ECS, Lambda, or any AWS service with an attached IAM role, no configuration is needed. The credentials are resolved automatically.

### Option B: AWS Profile (Recommended for Development)

1. Configure a named profile in `~/.aws/credentials`:

```ini
[deepcode-bedrock]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
region = us-east-1
```

2. Set the profile in `mcp_agent.secrets.yaml`:

```yaml
bedrock:
  profile: "deepcode-bedrock"
  aws_region: "us-east-1"
```

### Option C: Explicit Credentials

Add credentials directly in `mcp_agent.secrets.yaml`:

```yaml
bedrock:
  aws_region: "us-east-1"
  aws_access_key_id: "AKIAIOSFODNN7EXAMPLE"
  aws_secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  aws_session_token: ""  # Optional, for temporary credentials
```

### Option D: Environment Variables

Set standard AWS environment variables:

```bash
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_REGION="us-east-1"
```

## Step 4: Configure DeepCode to Use Bedrock

### Main Workflows (mcp-agent layer)

In `mcp_agent.config.yaml`:

```yaml
llm_provider: "bedrock"

bedrock:
  default_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  planning_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  implementation_model: "anthropic.claude-3-sonnet-20240229-v1:0"
  aws_region: "us-east-1"
```

### Nanobot Chatbot Layer

In your nanobot configuration, set the provider to bedrock:

```yaml
providers:
  bedrock:
    api_key: "your-aws-access-key-id"  # Maps to AWS_ACCESS_KEY_ID
    api_base: "us-east-1"              # Maps to AWS region
```

## Step 5: Verify Setup

Run the test suite to confirm everything works:

```bash
python -m pytest tests/test_bedrock_integration.py -v
```

## Troubleshooting

### "No AWS credentials found"

- Verify your credentials are configured (check `aws sts get-caller-identity`)
- Ensure `mcp_agent.secrets.yaml` has the bedrock section
- Check environment variables are set if using Option D

### "AccessDeniedException"

- Verify your IAM policy includes `bedrock:InvokeModel`
- Check you've enabled model access in the Bedrock console
- Ensure the model is available in your chosen region

### "ModelNotReadyException"

- The model may still be provisioning after enabling access
- Wait a few minutes and retry

### "ThrottlingException"

- You're hitting API rate limits
- DeepCode automatically retries with exponential backoff (up to 3 retries)
- Consider requesting a limit increase via AWS Support

### "ValidationException"

- Check your model ID is correct (see [Config Reference](bedrock_config_reference.md))
- Verify `max_tokens` doesn't exceed the model's limit
- Ensure message format is valid (user/assistant roles only)

### Region Not Supported

Not all AWS regions have Bedrock. Currently supported regions include:
- `us-east-1` (N. Virginia)
- `us-west-2` (Oregon)
- `eu-west-1` (Ireland)
- `ap-southeast-1` (Singapore)
- `ap-northeast-1` (Tokyo)

Check [AWS documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html) for the latest availability.
