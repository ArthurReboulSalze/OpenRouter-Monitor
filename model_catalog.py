"""OpenRouter catalog metadata, official rankings and promotion badges."""

import math
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

import requests

BASE_URL = "https://openrouter.ai/api/v1"
PROMOTIONS_URL = "https://openrouter.ai/collections/discounted-models"
REQUEST_TIMEOUT_SECONDS = 12
PROMOTION_MAX_AGE_SECONDS = 24 * 60 * 60
MODEL_CATEGORIES = {
    "all": "All models",
    "text": "Text",
    "image": "Image",
    "video": "Video",
    "speech": "Speech",
    "decisions": "Decisions",
    "embeddings": "Embeddings",
    "rerank": "Rerank",
    "transcription": "Transcription",
    "audio": "Audio",
}
SORT_COLUMNS = {"star", "idx", "name", "provider", "context", "input", "output", "popularity", "created", "promotion"}


def finite_number(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def creation_timestamp(value):
    number = finite_number(value)
    if number is not None and number > 0:
        return int(number)
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
                tzinfo=timezone.utc
            ).timestamp())
        except (ValueError, OverflowError):
            pass
    return None


def output_modalities(model):
    architecture = model.get("architecture") or {}
    modalities = model.get("output_modalities") or architecture.get("output_modalities")
    if not modalities and "->" in (architecture.get("modality") or ""):
        modalities = architecture["modality"].split("->", 1)[1].split("+")
    # Old monitor caches only contained the original text model catalog.
    if not modalities:
        return ["text"]
    if isinstance(modalities, str):
        modalities = re.split(r"[,+]", modalities)
    return list(dict.fromkeys(str(value).strip().lower() for value in modalities if value))


def enrich_model(model):
    normalized = dict(model)
    normalized["id"] = str(model.get("id") or "")
    normalized["name"] = str(model.get("name") or normalized["id"])
    normalized["name_lower"] = normalized["name"].lower()
    normalized["output_modalities"] = output_modalities(model)
    normalized["created"] = creation_timestamp(model.get("created"))
    try:
        normalized["created_text"] = datetime.fromtimestamp(
            normalized["created"], timezone.utc
        ).strftime("%Y-%m-%d") if normalized["created"] else "—"
    except (ValueError, OverflowError, OSError):
        normalized["created"] = None
        normalized["created_text"] = "—"
    rank = finite_number(model.get("popularity_rank"))
    normalized["popularity_rank"] = int(rank) if rank is not None and rank > 0 else None
    normalized["popularity_text"] = f"#{normalized['popularity_rank']:,}" if normalized["popularity_rank"] else "—"
    normalized["search_text"] = " ".join([
        normalized["name"], normalized["id"], str(model.get("description") or ""),
        " ".join(normalized["output_modalities"]),
    ]).lower()
    checked_at = finite_number(model.get("promotion_checked_at"))
    is_recent = checked_at is not None and 0 <= time.time() - checked_at <= PROMOTION_MAX_AGE_SECONDS
    normalized["is_promoted"] = bool(model.get("is_promoted")) if is_recent else False
    normalized["promotion_known"] = bool(model.get("promotion_known")) and is_recent
    discount = finite_number(model.get("discount_percent"))
    normalized["discount_percent"] = discount if normalized["is_promoted"] and discount is not None and 0 < discount <= 100 else None
    normalized["promotion_text"] = (
        f"* −{normalized['discount_percent']:g}%" if normalized["discount_percent"] is not None
        else "* Offer" if normalized["is_promoted"] else "—"
    )
    return normalized


def filter_models(models, query="", category="all", favorites=None, only_favorites=False, only_promotions=False):
    query = query.strip().lower()
    favorites = favorites or set()
    return [model for model in models
            if (category == "all" or category in model.get("output_modalities", ["text"]))
            and (not query or query in model.get("search_text", " ".join([model.get("name", ""), model.get("id", "")]).lower()))
            and (not only_favorites or model["id"] in favorites)
            and (not only_promotions or model.get("is_promoted", False))]


def sort_models(models, column, reverse=False, favorites=None):
    favorites = favorites or set()
    if column == "star":
        return sorted(models, key=lambda model: model["id"] not in favorites, reverse=reverse)
    if column == "name":
        return sorted(models, key=lambda model: model.get("name_lower", ""), reverse=reverse)
    if column == "provider":
        return sorted(models, key=lambda model: model["id"].lower(), reverse=reverse)
    field = {"context": "context_length", "input": "input_price", "output": "output_price",
             "popularity": "popularity_rank", "created": "created", "promotion": "discount_percent"}.get(column)
    if column == "promotion":
        offers = [model for model in models if model.get("is_promoted")]
        others = [model for model in models if not model.get("is_promoted")]
        offers.sort(key=lambda model: model.get("discount_percent") or 0, reverse=reverse)
        return offers + others
    if not field:
        return list(reversed(models)) if reverse else list(models)
    # Missing metadata must stay last in either direction.
    known = [model for model in models if finite_number(model.get(field)) is not None]
    unknown = [model for model in models if finite_number(model.get(field)) is None]
    return sorted(known, key=lambda model: float(model[field]), reverse=reverse) + unknown


class PromotionParser(HTMLParser):
    """Read model headings and their explicit discount badges, ignoring descriptions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.promotions = {}
        self.current_model = None
        self.anchor = None
        self.badge_depth = 0
        self.badge_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.anchor = attrs.get("href")
        elif tag == "h3" and self.anchor:
            path = unquote(urlsplit(self.anchor).path).strip("/")
            if len(path.split("/")) == 2:
                self.current_model = path
        if tag == "span":
            if self.badge_depth:
                self.badge_depth += 1
            elif self.current_model and "text-positive-text" in attrs.get("class", "").split():
                self.badge_depth = 1
                self.badge_text = []

    def handle_data(self, data):
        if self.badge_depth:
            self.badge_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            self.anchor = None
        elif tag == "span" and self.badge_depth:
            self.badge_depth -= 1
            if not self.badge_depth:
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s+off\s*", "".join(self.badge_text), re.I)
                if match and 0 < float(match[1]) <= 100:
                    self.promotions[self.current_model] = float(match[1])


def parse_promotions(html):
    parser = PromotionParser()
    parser.feed(html)
    if not parser.promotions and not re.search(r'"numberOfItems"\s*:\s*0\b', html):
        raise ValueError("OpenRouter promotion collection could not be read")
    return parser.promotions


def fetch_catalog(api_key=None):
    """Fetch all modalities in the official popularity order, including pagination."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    params = {"output_modalities": "all", "sort": "most-popular"}
    models = []
    seen_models = set()
    seen_pages = set()
    url = f"{BASE_URL}/models"
    with requests.Session() as session:
        while url:
            if url in seen_pages or urlsplit(url).netloc != "openrouter.ai" or urlsplit(url).scheme != "https":
                raise ValueError("Invalid catalog pagination link")
            seen_pages.add(url)
            response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("Invalid OpenRouter catalog response")
            for model in payload["data"]:
                if not isinstance(model, dict) or not model.get("id") or model["id"] in seen_models:
                    continue
                seen_models.add(model["id"])
                models.append({**model, "popularity_rank": len(models) + 1})
            next_page = (payload.get("links") or {}).get("next")
            if next_page:
                from urllib.parse import urljoin
                url = urljoin(url, next_page)
                params = None
            else:
                url = None
        try:
            response = session.get(PROMOTIONS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            promotions = parse_promotions(response.text)
        except (requests.RequestException, ValueError):
            promotions = None
    checked_at = time.time()
    for model in models:
        aliases = [model["id"], model.get("canonical_slug")]
        discount = next((promotions[alias] for alias in aliases if alias in promotions), None) if promotions is not None else None
        model.update({"is_promoted": discount is not None, "discount_percent": discount,
                      "promotion_known": promotions is not None, "promotion_checked_at": checked_at})
    return models
