"""
AWS Bedrock utility functions for credential management and model access.

Provides helpers for resolving AWS credentials, validating Bedrock access,
mapping friendly model names to Bedrock model IDs, and listing available models.
"""

import logging
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

BEDROCK_MODEL_MAP = {
    "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
}


def get_bedrock_session(config: dict[str, Any]) -> boto3.Session:
    """Create a boto3 Session using the configured credential chain.

    Credential resolution priority:
        1. IAM role (EC2/ECS/Lambda) - automatic via default provider chain
        2. AWS profile specified in config["aws_profile"]
        3. Explicit credentials from config["aws_access_key_id"] and
           config["aws_secret_access_key"] (and optional config["aws_session_token"])
        4. Environment variables (AWS_ACCESS_KEY_ID, etc.) - boto3 default fallback

    Args:
        config: Dictionary that may contain ``aws_profile``, ``aws_access_key_id``,
            ``aws_secret_access_key``, ``aws_session_token``, and ``aws_region``.

    Returns:
        A configured :class:`boto3.Session`.

    Raises:
        NoCredentialsError: If no valid credentials can be resolved.
    """
    region = config.get("aws_region", "us-east-1")

    # Priority 1: IAM role — attempt default credential chain first.
    # If running on EC2/ECS/Lambda the instance metadata service will provide creds.
    try:
        session = boto3.Session(region_name=region)
        credentials = session.get_credentials()
        if credentials is not None:
            # Resolve to check they are usable (non-None access key).
            resolved = credentials.get_frozen_credentials()
            if resolved.access_key:
                logger.debug("Using credentials from default provider chain (IAM role / env).")
                return session
    except (BotoCoreError, Exception):
        pass

    # Priority 2: Named AWS profile from config.
    aws_profile = config.get("aws_profile")
    if aws_profile:
        try:
            session = boto3.Session(profile_name=aws_profile, region_name=region)
            logger.debug("Using AWS profile '%s'.", aws_profile)
            return session
        except BotoCoreError as exc:
            logger.warning("Failed to create session with profile '%s': %s", aws_profile, exc)

    # Priority 3: Explicit credentials from config / secrets.
    access_key = config.get("aws_access_key_id")
    secret_key = config.get("aws_secret_access_key")
    if access_key and secret_key:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=config.get("aws_session_token"),
            region_name=region,
        )
        logger.debug("Using explicit AWS credentials from config.")
        return session

    # Priority 4: Fall back to environment variables (boto3 handles this automatically).
    session = boto3.Session(region_name=region)
    logger.debug("Falling back to environment-variable credentials.")
    return session


def validate_bedrock_credentials(session: boto3.Session, region: Optional[str] = None) -> bool:
    """Validate that the session has working credentials for Amazon Bedrock.

    Attempts a lightweight ``list_foundation_models`` call to confirm both
    credential validity and Bedrock service access.

    Args:
        session: A :class:`boto3.Session` to validate.
        region: AWS region override.  If ``None`` the session's region is used.

    Returns:
        ``True`` if credentials are valid and Bedrock is accessible.

    Raises:
        NoCredentialsError: If the session has no credentials at all.
        ClientError: If the credentials lack permission for Bedrock, or for
            other AWS API errors (access denied, invalid region, etc.).
    """
    try:
        client = session.client("bedrock", region_name=region)
        client.list_foundation_models(maxResults=1)
        logger.info("Bedrock credentials validated successfully.")
        return True
    except NoCredentialsError:
        raise NoCredentialsError(
            "No AWS credentials found. Configure credentials via IAM role, "
            "AWS profile, explicit keys, or environment variables."
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            raise ClientError(
                exc.response,
                "bedrock:ListFoundationModels — your credentials lack permission "
                "to access Amazon Bedrock. Ensure the IAM policy includes "
                "bedrock:ListFoundationModels.",
            )
        raise


def map_model_id(model_name: str) -> str:
    """Convert a friendly model name to its full Bedrock model ID.

    Args:
        model_name: A short name (e.g. ``"claude-3-5-sonnet"``) or an
            already-qualified Bedrock model ID.

    Returns:
        The full Bedrock model identifier string.

    Raises:
        ValueError: If *model_name* is not recognised and does not look like
            a fully-qualified Bedrock model ID.
    """
    if model_name in BEDROCK_MODEL_MAP:
        return BEDROCK_MODEL_MAP[model_name]

    # Allow pass-through of fully-qualified IDs (e.g. "anthropic.claude-...").
    if "." in model_name:
        return model_name

    available = ", ".join(sorted(BEDROCK_MODEL_MAP.keys()))
    raise ValueError(
        f"Unknown model name '{model_name}'. "
        f"Available friendly names: {available}. "
        f"You can also pass a fully-qualified Bedrock model ID directly."
    )


def get_available_bedrock_models(
    session: boto3.Session, region: Optional[str] = None
) -> list[dict[str, str]]:
    """List foundation models available in the caller's Bedrock account.

    Args:
        session: An authenticated :class:`boto3.Session`.
        region: AWS region override.  If ``None`` the session's region is used.

    Returns:
        A list of dicts, each containing ``modelId``, ``modelName``, and
        ``providerName`` for every available foundation model.

    Raises:
        ClientError: On permission or service errors.
    """
    try:
        client = session.client("bedrock", region_name=region)
        response = client.list_foundation_models()
        models = []
        for summary in response.get("modelSummaries", []):
            models.append(
                {
                    "modelId": summary["modelId"],
                    "modelName": summary.get("modelName", ""),
                    "providerName": summary.get("providerName", ""),
                }
            )
        logger.info("Found %d available Bedrock models.", len(models))
        return models
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            logger.error(
                "Access denied when listing Bedrock models. "
                "Ensure your IAM policy includes bedrock:ListFoundationModels."
            )
        raise
