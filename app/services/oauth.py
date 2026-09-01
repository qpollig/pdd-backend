from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.user import OAuthProvider


@dataclass
class OAuthProfile:
    oauth_id: str
    name: str | None
    email: str | None
    avatar_url: str | None


class OAuthError(Exception):
    pass


async def exchange_code_and_fetch_profile(provider: OAuthProvider, code: str, redirect_uri: str) -> OAuthProfile:
    """Обменивает code провайдера на access_token и запрашивает профиль пользователя."""
    if provider == OAuthProvider.yandex:
        return await _yandex_profile(code, redirect_uri)
    if provider == OAuthProvider.vk:
        return await _vk_profile(code, redirect_uri)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNSUPPORTED_PROVIDER")


async def _yandex_profile(code: str, redirect_uri: str) -> OAuthProfile:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://oauth.yandex.ru/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.YANDEX_CLIENT_ID,
                "client_secret": settings.YANDEX_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            raise OAuthError(f"Yandex token exchange failed: {token_resp.text}")
        access_token = token_resp.json()["access_token"]

        info_resp = await client.get(
            "https://login.yandex.ru/info",
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
        )
        if info_resp.status_code != 200:
            raise OAuthError(f"Yandex profile fetch failed: {info_resp.text}")
        data = info_resp.json()

    return OAuthProfile(
        oauth_id=str(data["id"]),
        name=data.get("real_name") or data.get("display_name"),
        email=data.get("default_email"),
        avatar_url=(
            f"https://avatars.yandex.net/get-yapic/{data['default_avatar_id']}/islands-200"
            if data.get("default_avatar_id")
            else None
        ),
    )


async def _vk_profile(code: str, redirect_uri: str) -> OAuthProfile:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.get(
            "https://oauth.vk.com/access_token",
            params={
                "client_id": settings.VK_CLIENT_ID,
                "client_secret": settings.VK_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        if token_resp.status_code != 200:
            raise OAuthError(f"VK token exchange failed: {token_resp.text}")
        token_data = token_resp.json()
        access_token = token_data["access_token"]
        vk_user_id = token_data["user_id"]
        email = token_data.get("email")

        info_resp = await client.get(
            "https://api.vk.com/method/users.get",
            params={
                "user_ids": vk_user_id,
                "fields": "photo_200",
                "access_token": access_token,
                "v": "5.199",
            },
        )
        if info_resp.status_code != 200:
            raise OAuthError(f"VK profile fetch failed: {info_resp.text}")
        response_items = info_resp.json().get("response", [])
        data = response_items[0] if response_items else {}

    full_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])) or None

    return OAuthProfile(
        oauth_id=str(vk_user_id),
        name=full_name,
        email=email,
        avatar_url=data.get("photo_200"),
    )
