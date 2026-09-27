from typing import Literal, Optional
from pydantic import BaseModel, Field

NodeType = Literal["flight", "train", "hotel", "transfer", "activity", "event"]
NodeStatus = Literal["safe", "at_risk", "broken", "cancelled"]
EdgeType = Literal["sequential", "transfer_required", "checkin_dependency", "same_day"]


class BookingNode(BaseModel):
    id: str
    type: NodeType
    title: str
    location: str
    start: str  # ISO datetime
    end: str  # ISO datetime
    cost: float
    provider: str
    cancellation_policy: str  # e.g. "free_24h", "non_refundable", "partial_50pct"
    status: NodeStatus = "safe"
    weather_sensitive: bool = False  # outdoor bookings that a weather event can cancel/delay
    # geo position (start point); transport legs also carry their destination - used by the
    # digital twin for per-location live weather and by the map view
    lat: Optional[float] = None
    lon: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lon: Optional[float] = None

    # --- money (all user-entered, INR) ---
    # fixed charge if the TRAVELER cancels; overrides the cancellation_policy percentage
    cancellation_penalty: Optional[float] = Field(default=None, ge=0)
    # how a refund comes back: cash to the original payment method, a provider credit/voucher, or nothing
    refund_mode: Literal["cash", "credit", "none"] = "cash"

    # --- monitoring ---
    service_code: Optional[str] = None  # flight/train number for live status checks, e.g. "6E204"

    # --- recovery ---
    # replacement options for this booking (entered by the user or from a catalog); when empty,
    # the recovery engine falls back to clearly-labelled estimate templates for the booking type
    alternatives: list[dict] = Field(default_factory=list)
    # the engine never books or pays: a replacement stays "pending_manual_booking" until the
    # traveler confirms they booked it themselves
    booking_status: Literal["confirmed", "pending_manual_booking", "dropped"] = "confirmed"


class DependencyEdge(BaseModel):
    source: str
    target: str
    type: EdgeType
    buffer_minutes: int  # minimum gap required between source.end and target.start


class DisruptionRequest(BaseModel):
    node_id: str
    kind: Literal["delay", "cancel"]
    delay_minutes: Optional[int] = 0
    reason: Optional[str] = "unspecified"


class WeatherDisruptionRequest(BaseModel):
    date: str  # "YYYY-MM-DD" - every booking starting that day is evaluated
    severity: Literal["moderate", "severe"] = "moderate"


class CreateTripRequest(BaseModel):
    name: str = "My Trip"


class RecoveryOption(BaseModel):
    node_id: str
    replacement_title: str
    provider: str
    cost: float
    start: str
    end: str
    notes: str
    # keep: same booking, just late | reschedule: same provider moves it (fee, no refund) |
    # rebook / manual_booking: a new booking (old one refunded per its terms) | drop: give it up
    action: Literal["keep", "reschedule", "rebook", "manual_booking", "drop"] = "rebook"
    requires_manual_booking: bool = False
    price_source: str = "catalog"  # "user-entered" | "catalog" | "estimate" | provider name
    original_cost: float = 0.0
    price_vs_original: float = 0.0  # replacement cost - original user-entered cost
    market_price: Optional[float] = None  # external quote when a price provider is configured
    market_price_source: str = "unavailable"


class RecoveryPlan(BaseModel):
    id: str
    label: str
    options: list[RecoveryOption]
    total_cost_delta: float
    total_time_delta_minutes: int
    convenience_score: float  # 0-100, higher is better
    pct_itinerary_affected: float
    refund_recovered: float
    score: float  # weighted composite 0-100, higher is better
    category: Literal["balanced", "cheapest", "fastest", "alternative"] = "alternative"
    badges: list[str] = Field(default_factory=list)  # every category this exact plan wins
    score_breakdown: dict = Field(default_factory=dict)  # per-objective value / normalized / weight / contribution
    money: dict = Field(default_factory=dict)  # penalties, cash refund, credit, new spend, net
    action_items: list[str] = Field(default_factory=list)  # what the traveler must book/cancel themselves


class RiskWarning(BaseModel):
    node_id: str
    title: str
    message: str
    severity: Literal["low", "medium", "high"]


class TravelerPreferences(BaseModel):
    """Weights and hard constraints the traveler cares about when recovery plans are
    generated and ranked. Weights don't need to sum to 1 - they're normalized before use,
    so e.g. doubling every weight has no effect but changing their relative proportion does."""
    cost_weight: float = Field(default=0.2, ge=0, le=1)
    time_weight: float = Field(default=0.3, ge=0, le=1)
    convenience_weight: float = Field(default=0.4, ge=0, le=1)
    disruption_weight: float = Field(default=0.1, ge=0, le=1)
    min_rating: float = Field(default=0, ge=0, le=100)  # exclude alternatives rated below this
    avoid_next_day: bool = False  # exclude alternatives that push into the following day


class TwinOverrides(BaseModel):
    """What-if weather parameters; any left unset keep the live forecast value."""
    rain_mm_h: Optional[float] = Field(default=None, ge=0, le=200)
    storm_hours: Optional[float] = Field(default=None, ge=0, le=96)
    temp_c: Optional[float] = Field(default=None, ge=-10, le=55)
    wind_kmh: Optional[float] = Field(default=None, ge=0, le=250)
    flood_index: Optional[float] = Field(default=None, ge=0, le=1)
    social_index: Optional[float] = Field(default=None, ge=0, le=1)


class TwinScenario(BaseModel):
    overrides: TwinOverrides = Field(default_factory=TwinOverrides)
    target_place: str = "all"  # "all" or a place name from the twin state
    target_date: Optional[str] = None  # "YYYY-MM-DD"; None = whole trip


class TwinObservation(BaseModel):
    node_id: str
    delay_minutes: float = Field(ge=0, le=2000)
