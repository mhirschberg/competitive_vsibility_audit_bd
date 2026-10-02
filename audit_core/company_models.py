"""Shared Pydantic schemas for company research and buyer-intent keywords."""

from pydantic import BaseModel, Field


class BuyerIntentKeyword(BaseModel):
    keyword: str
    intent: str = "commercial"
    rationale: str = ""


class BrandAnalysis(BaseModel):
    brand_name: str
    official_url: str
    domain: str
    category: str = ""
    description: str = ""
    positioning: str = ""
    primary_market_role: str = "other"
    secondary_market_roles: list[str] = Field(default_factory=list)
    offering_type: str = ""
    value_chain_position: str = ""
    substitute_definition: str = ""
    classification_confidence: float = 0.0
    classification_evidence: list[str] = Field(default_factory=list)
    target_customers: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class CompanyIntake(BaseModel):
    brand: BrandAnalysis
    buyer_intent_keywords: list[BuyerIntentKeyword] = Field(default_factory=list)
