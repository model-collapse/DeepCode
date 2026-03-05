# Migrating to AWS Bedrock

Guide for migrating from the direct Anthropic API to AWS Bedrock in DeepCode.

## Why Migrate?

| Factor | Direct Anthropic API | AWS Bedrock |
|--------|---------------------|-------------|
| Billing | Anthropic account + API key | AWS account (consolidated billing) |
| Authentication | API key | IAM roles, profiles, or access keys |
| Data residency | Anthropic infrastructure | Your chosen AWS region |
| Compliance | Anthropic's terms | AWS compliance certifications (SOC, HIPAA, etc.) |
| Network | Public internet | VPC endpoints available |
| Rate limits | Anthropic account limits | AWS service quotas (adjustable) |
| Model access | Immediate | Requires enabling in Bedrock console |

## Migration Steps

### 1. Enable Bedrock Access

Follow [Step 1 and Step 2 of the Setup Guide](bedrock_setup_guide.md#step-1-enable-bedrock-model-access) to enable model access and configure IAM permissions.

### 2. Update Secrets Configuration

**Before** (`mcp_agent.secrets.yaml`):
```yaml
anthropic:
  api_key: "sk-ant-your-key-here"
```

**After** (`mcp_agent.secrets.yaml`):
```yaml
anthropic:
  api_key: "sk-ant-your-key-here"  # Keep as fallback if desired
bedrock:
  aws_region: "us-east-1"
  aws_access_key_id: "AKIAIOSFODNN7EXAMPLE"
  aws_secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

### 3. Update Provider Configuration

**Before** (`mcp_agent.config.yaml`):
```yaml
llm_provider: "anthropic"

anthropic:
  default_model: "claude-sonnet-4.5"
  planning_model: "claude-sonnet-4.5"
  implementation_model: "claude-sonnet-3.5"
```

**After** (`mcp_agent.config.yaml`):
```yaml
llm_provider: "bedrock"

bedrock:
  default_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  planning_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"
  implementation_model: "anthropic.claude-3-sonnet-20240229-v1:0"
  aws_region: "us-east-1"
```

### 4. Model Name Mapping

Anthropic API model names differ from Bedrock model IDs:

| Anthropic API | Bedrock Model ID |
|--------------|-----------------|
| `claude-sonnet-4.5` | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `claude-3-opus-20240229` | `anthropic.claude-3-opus-20240229-v1:0` |
| `claude-3-sonnet-20240229` | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `claude-3-haiku-20240307` | `anthropic.claude-3-haiku-20240307-v1:0` |

You can also use the short names (`claude-3-5-sonnet`, `claude-3-opus`, etc.) and DeepCode will map them automatically.

### 5. Verify the Migration

```bash
# Run the integration tests
python -m pytest tests/test_bedrock_integration.py -v

# Test with a simple query to verify end-to-end
python -c "
import asyncio
from utils.augmented_llm_bedrock import BedrockAugmentedLLM

async def test():
    llm = BedrockAugmentedLLM()
    result = await llm.generate_str('Say hello in one word.')
    print('Response:', result)

asyncio.run(test())
"
```

## Feature Parity

### Supported Features

| Feature | Direct API | Bedrock | Notes |
|---------|-----------|---------|-------|
| Chat completions | Yes | Yes | Full parity |
| System prompts | Yes | Yes | Passed via `system` parameter |
| Tool calling | Yes | Yes | Same Anthropic format |
| Streaming | Yes | Yes | Via `invoke_model_with_response_stream` |
| Temperature control | Yes | Yes | |
| Max tokens | Yes | Yes | |
| Multiple content blocks | Yes | Yes | Text + tool_use |

### Differences

- **Authentication**: Bedrock uses AWS credentials instead of API keys
- **Model IDs**: Bedrock uses qualified IDs (e.g., `anthropic.claude-3-5-sonnet-20241022-v2:0`)
- **API version**: Bedrock requests include `anthropic_version: "bedrock-2023-05-31"`
- **Rate limiting**: Managed by AWS service quotas, not Anthropic account limits
- **Retry behavior**: DeepCode's Bedrock wrapper includes built-in retry with exponential backoff

### Not Yet Supported via Bedrock

- **Vision/image inputs**: Requires image preprocessing specific to Bedrock's format
- **Batch API**: Bedrock has its own batch inference API with different semantics

## Rollback

To switch back to the direct Anthropic API:

1. Change `llm_provider` back to `"anthropic"` in `mcp_agent.config.yaml`
2. Ensure your Anthropic API key is still configured in `mcp_agent.secrets.yaml`

The Bedrock configuration can remain in place without causing issues.

## Cost Considerations

- Bedrock pricing is per-token, similar to the direct Anthropic API
- Bedrock prices may differ slightly from Anthropic's direct pricing
- No minimum commitment for on-demand usage
- Provisioned Throughput is available for high-volume workloads at discounted rates
- Check [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) for current rates
- AWS consolidated billing can simplify cost management across teams
