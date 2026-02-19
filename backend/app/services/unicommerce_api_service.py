"""
Unicommerce Generic API Service
================================
Provides a reusable HTTP client for ALL Unicommerce REST APIs.
Uses the centralized TokenManager for authentication.

Supports:
- Tenant-level APIs (no Facility header)
- Facility-level APIs (requires Facility header)
- POST and GET methods
- Automatic retry on 401 (token refresh)
"""

import httpx
import logging
from typing import Any, Dict, Optional

from app.core.token_manager import get_token_manager
from app.core.config import settings

logger = logging.getLogger(__name__)


class UnicommerceAPIService:
    """
    Generic Unicommerce API client.
    All Unicommerce endpoints follow a consistent pattern:
    - POST with JSON payload to /services/rest/v1/...
    - Bearer token auth
    - Optional Facility header for facility-level APIs
    """

    def __init__(self):
        self.token_manager = get_token_manager()
        self.tenant = self.token_manager.tenant
        self.base_url = f"https://{self.tenant}.unicommerce.com"
        self.api_base = f"{self.base_url}/services/rest/v1"
        self.timeout = httpx.Timeout(60.0, connect=15.0)
        self.limits = httpx.Limits(
            max_connections=50, max_keepalive_connections=20)

    async def _get_headers(self, facility_code: Optional[str] = None) -> Dict[str, str]:
        """Get authenticated headers, optionally with Facility header."""
        headers = await self.token_manager.get_headers()
        if facility_code:
            headers["Facility"] = facility_code
        return headers

    async def post(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        facility_code: Optional[str] = None,
        use_full_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Make an authenticated POST request to a Unicommerce API endpoint.

        Args:
            endpoint: API path, e.g. '/oms/saleOrder/create'
            payload: JSON body
            facility_code: Optional facility code for facility-level APIs
            use_full_url: If True, endpoint is treated as a full URL path from base
        """
        url = endpoint if use_full_url else f"{self.api_base}{endpoint}"
        headers = await self._get_headers(facility_code)

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)

                # Retry once on 401 (token expired)
                if response.status_code == 401:
                    logger.warning(
                        "Got 401, invalidating and refreshing token...")
                    # Invalidate current token to force refresh
                    self.token_manager.invalidate_token()
                    # Get new token
                    new_token = await self.token_manager.get_valid_token()
                    if new_token:
                        # Get fresh headers with new token
                        headers = await self._get_headers(facility_code)
                        # Retry with new token
                        response = await client.post(url, json=payload, headers=headers)
                    else:
                        logger.error("Failed to refresh token")

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                error_body = ""
                try:
                    error_body = e.response.text[:500]
                except Exception:
                    pass
                logger.error(
                    f"HTTP {e.response.status_code} for {endpoint}: {error_body}")
                return {
                    "successful": False,
                    "error": f"HTTP {e.response.status_code}",
                    "detail": error_body,
                }
            except httpx.TimeoutException:
                logger.error(f"Timeout for {endpoint}")
                return {"successful": False, "error": "Request timed out"}
            except Exception as e:
                logger.error(f"Error calling {endpoint}: {e}", exc_info=True)
                return {"successful": False, "error": str(e)}

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        facility_code: Optional[str] = None,
        use_full_url: bool = False,
    ) -> Any:
        """
        Make an authenticated GET request to a Unicommerce API endpoint.

        Args:
            endpoint: API path, e.g. '/oms/invoice/show'
            params: Query parameters
            facility_code: Optional facility code for facility-level APIs
            use_full_url: If True, endpoint is treated as a full URL path from base
        """
        url = endpoint if use_full_url else f"{self.api_base}{endpoint}"
        headers = await self._get_headers(facility_code)

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                response = await client.get(url, params=params, headers=headers)

                # Retry on 401
                if response.status_code == 401:
                    logger.warning(
                        "Got 401, invalidating and refreshing token...")
                    self.token_manager.invalidate_token()
                    new_token = await self.token_manager.get_valid_token()
                    if new_token:
                        headers = await self._get_headers(facility_code)
                        response = await client.get(url, params=params, headers=headers)
                    else:
                        logger.error("Failed to refresh token")

                response.raise_for_status()

                # Try JSON first, fall back to raw content
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()
                elif "application/pdf" in content_type:
                    return {
                        "successful": True,
                        "content_type": "application/pdf",
                        "content": response.content,
                        "content_length": len(response.content),
                    }
                else:
                    return {
                        "successful": True,
                        "content_type": content_type,
                        "text": response.text[:5000],
                    }

            except httpx.HTTPStatusError as e:
                error_body = ""
                try:
                    error_body = e.response.text[:500]
                except Exception:
                    pass
                logger.error(
                    f"HTTP {e.response.status_code} for {endpoint}: {error_body}")
                return {
                    "successful": False,
                    "error": f"HTTP {e.response.status_code}",
                    "detail": error_body,
                }
            except httpx.TimeoutException:
                logger.error(f"Timeout for {endpoint}")
                return {"successful": False, "error": "Request timed out"}
            except Exception as e:
                logger.error(f"Error calling {endpoint}: {e}", exc_info=True)
                return {"successful": False, "error": str(e)}

    async def get_raw(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        facility_code: Optional[str] = None,
    ) -> httpx.Response:
        """
        Make an authenticated GET request and return the raw httpx.Response.
        Useful for PDF/binary downloads.
        """
        url = f"{self.api_base}{endpoint}"
        headers = await self._get_headers(facility_code)

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 401:
                    self.token_manager.invalidate_token()
                    await self.token_manager.get_valid_token()
                    headers = await self._get_headers(facility_code)
                    response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response
            except httpx.TimeoutException:
                logger.error(f"Timeout for GET {endpoint}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP {e.response.status_code} for GET {endpoint}")
                raise
            except Exception as e:
                logger.error(f"Error calling GET {endpoint}: {e}", exc_info=True)
                raise


# =========================================================================
# SINGLETON
# =========================================================================

_uc_api_service: Optional[UnicommerceAPIService] = None


def get_uc_api_service() -> UnicommerceAPIService:
    """Get or create the global Unicommerce API service singleton."""
    global _uc_api_service
    if _uc_api_service is None:
        _uc_api_service = UnicommerceAPIService()
    return _uc_api_service
