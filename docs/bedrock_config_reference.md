# AWS Bedrock Configuration Reference

Complete reference for all Bedrock-related configuration options in DeepCode.

## Configuration Files

### mcp_agent.config.yaml

```yaml
# Set Bedrock as the LLM provider
llm_provider: "bedrock"

bedrock:
  default_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  planning_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  implementation_model: "anthropic.claude-3-sonnet-20240229-v1:0"
  aws_region: "us-east-1"
  base_max_tokens: 20000
  retry_max_tokens: 15000
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_model` | string | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Default model for general use |
| `planning_model` | string | Same as `default_model` | Model used for planning/analysis phases |
| `implementation_model` | string | Same as `default_model` | Model used for code generation |
| `aws_region` | string | `us-east-1` | AWS region for Bedrock API calls |
| `base_max_tokens` | int | `20000` | Max tokens for initial requests |
| `retry_max_tokens` | int | `15000` | Reduced max tokens for retry requests |

### mcp_agent.secrets.yaml

```yaml
bedrock:
  aws_region: "us-east-1"
  aws_access_key_id: ""
  aws_secret_access_key: ""
  aws_session_token: ""   # Optional, for temporary/STS credentials
  profile: ""             # AWS CLI profile name (alternative to explicit keys)
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `aws_region` | string | `us-east-1` | AWS region (also settable via `AWS_REGION` env var) |
| `aws_access_key_id` | string | `""` | AWS access key (also via `AWS_ACCESS_KEY_ID`) |
| `aws_secret_access_key` | string | `""` | AWS secret key (also via `AWS_SECRET_ACCESS_KEY`) |
| `aws_session_token` | string | `""` | STS session token (also via `AWS_SESSION_TOKEN`) |
| `profile` | string | `""` | AWS CLI profile name from `~/.aws/credentials` |

## Model ID Reference

### Short Names (Friendly)

DeepCode maps these short names to full Bedrock model IDs automatically:

| Short Name | Full Bedrock Model ID |
|------------|----------------------|
| `claude-3-5-sonnet` | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `claude-3-opus` | `anthropic.claude-3-opus-20240229-v1:0` |
| `claude-3-sonnet` | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `claude-3-haiku` | `anthropic.claude-3-haiku-20240307-v1:0` |

### Full Model IDs

You can also use fully-qualified Bedrock model IDs directly (any string containing a `.` is treated as a full ID):

```yaml
bedrock:
  default_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
```

### Model Capabilities

| Model | Best For | Max Output Tokens | Context Window |
|-------|----------|-------------------|----------------|
| Claude 3.5 Sonnet | General purpose, code generation | 8,192 | 200K |
| Claude 3 Opus | Complex reasoning, analysis | 4,096 | 200K |
| Claude 3 Sonnet | Balanced performance/cost | 4,096 | 200K |
| Claude 3 Haiku | Fast responses, simple tasks | 4,096 | 200K |

## Credential Resolution Priority

When resolving AWS credentials, DeepCode checks in this order:

1. **IAM Role** - Automatic on EC2/ECS/Lambda via instance metadata
2. **AWS Profile** - Named profile from `mcp_agent.secrets.yaml` (`profile` field)
3. **Explicit Credentials** - `aws_access_key_id` + `aws_secret_access_key` from secrets
4. **Environment Variables** - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key ID |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key |
| `AWS_SESSION_TOKEN` | Session token for temporary credentials |
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `AWS_PROFILE` | AWS CLI profile name |

## Nanobot Provider Registry

Bedrock is registered in the nanobot provider system with:

| Property | Value |
|----------|-------|
| Name | `bedrock` |
| Keywords | `bedrock`, `aws` |
| LiteLLM Prefix | `bedrock` |
| Display Name | `AWS Bedrock` |

Models are prefixed with `bedrock/` for LiteLLM routing (e.g., `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`).

## Retry Behavior

The `BedrockAugmentedLLM` wrapper automatically retries on transient errors:

| Setting | Value |
|---------|-------|
| Max retries | 3 |
| Initial backoff | 1.0s |
| Backoff multiplier | 2.0x |
| Retryable errors | `ThrottlingException`, `ServiceUnavailableException`, `ModelTimeoutException` |

Non-retryable errors (e.g., `ValidationException`, `AccessDeniedException`) fail immediately.

## Region Availability

Bedrock availability varies by region. Common regions with Claude model support:

| Region | Code | Claude 3.5 Sonnet | Claude 3 Opus | Claude 3 Sonnet | Claude 3 Haiku |
|--------|------|-------------------|---------------|-----------------|----------------|
| US East (N. Virginia) | `us-east-1` | Yes | Yes | Yes | Yes |
| US West (Oregon) | `us-west-2` | Yes | Yes | Yes | Yes |
| Europe (Ireland) | `eu-west-1` | Yes | - | Yes | Yes |
| Asia Pacific (Singapore) | `ap-southeast-1` | Yes | - | Yes | Yes |
| Asia Pacific (Tokyo) | `ap-northeast-1` | Yes | - | Yes | Yes |

Check the [AWS Bedrock documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html) for current availability.
