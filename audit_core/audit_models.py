"""Shared provider-neutral models used across audit stages."""

from pydantic import BaseModel, Field


class CompetitorCandidate(BaseModel):
    domain: str
    preferred_hostname: str
    homepage_url: str
    frequency: int
    keyword_coverage: float
    best_rank: int
    average_rank: float
    rank_score: float
    total_score: float
    matched_keywords: list[str] = Field(default_factory=list)
    serp_urls: list[str] = Field(default_factory=list)
    serp_titles: list[str] = Field(default_factory=list)


class SelectedCompetitor(BaseModel):
    brand_name: str
    domain: str
    official_url: str
    reason: str = ""
    confidence: float = 0.0


class BrandProfile(BaseModel):
    brand_name: str
    official_url: str
    domain: str
    category: str = ""
    positioning: str = ""
    target_customers: list[str] = Field(default_factory=list)
    relevant_products: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    pricing_model: str = "unknown"
    competitor_reason: str = ""
    direct_competitor: bool = True
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
