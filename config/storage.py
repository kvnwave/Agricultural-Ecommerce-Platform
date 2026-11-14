"""Storage helpers shared by settings and tests."""

from urllib.parse import urlparse


def supabase_storage_options(
    *,
    endpoint,
    bucket,
    access_key,
    secret_key,
    region,
    custom_domain="",
    querystring_auth=False,
):
    """Build django-storages options for Supabase's S3-compatible endpoint.

    Public buckets need Supabase's object/public URL, not the S3 API URL.
    Private buckets keep signed S3 URLs and must not set a custom domain.
    """

    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("SUPABASE_S3_ENDPOINT must be an absolute URL.")
    if not bucket:
        raise ValueError("SUPABASE_BUCKET must not be empty.")

    options = {
        "bucket_name": bucket,
        "endpoint_url": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "region_name": region,
        "file_overwrite": False,
        # Supabase requires path-style S3 URLs and SigV4 signing.
        "addressing_style": "path",
        "signature_version": "s3v4",
        "querystring_auth": querystring_auth,
    }

    if querystring_auth:
        return options

    public_domain = custom_domain.strip()
    for prefix in ("https://", "http://"):
        public_domain = public_domain.removeprefix(prefix)
    public_domain = public_domain.rstrip("/")

    options["custom_domain"] = public_domain or (
        f"{parsed.netloc}/storage/v1/object/public/{bucket}"
    )
    return options
