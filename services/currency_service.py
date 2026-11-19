"""Currency conversion deliberately fails closed without a configured verified feed."""
from typing import Any

def get_currency_conversion(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    """Do not infer exchange rates; present an explicit unavailable result."""
    return {"amount":amount,"from_currency":from_currency.upper(),"to_currency":to_currency.upper(),
            "converted_amount":None,"rate":None,"rate_date":None,"source":None,
            "status":"conversion unavailable: no verified free exchange-rate provider configured"}
