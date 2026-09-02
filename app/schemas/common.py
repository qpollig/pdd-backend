from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Единый формат ошибок API: {"detail": "КОД_ОШИБКИ"}. Конкретные коды для каждого
    эндпоинта см. в description соответствующего response в Swagger, либо в docs/API_ERRORS.md."""

    detail: str
