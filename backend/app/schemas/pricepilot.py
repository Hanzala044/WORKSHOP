from pydantic import Field, field_validator

from app.core.currencies import CURRENCY_CODES

from app.schemas.common import StrictModel


class ProductRequest(StrictModel):
    url: str = Field(min_length=1, max_length=4096)
    name_selector: str = Field(default="h1", min_length=1, max_length=500)
    price_selector: str = Field(min_length=1, max_length=500)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value):
        if value is not None and value not in CURRENCY_CODES:
            raise ValueError("Use a supported ISO 4217 fiat currency code")
        return value


class CompareRequest(StrictModel):
    items: list[ProductRequest] = Field(min_length=1, max_length=10)
    permission_confirmed: bool = False
