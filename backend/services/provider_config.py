"""Environment-backed configuration for PongDang's external data providers.

Only configuration presence is safe to expose publicly. Credential values stay on
the Django side and must never be serialized into API responses or frontend code.
"""

from dataclasses import dataclass

from decouple import config


def _read_key(name: str, fallback: str = "") -> str:
    """Read and normalize a provider credential without logging its value."""

    return config(name, default="").strip() or fallback.strip()


@dataclass(frozen=True)
class ProviderConfig:
    data_go_kr: str
    tour_api: str
    kma: str
    khoa: str
    moe: str

    @classmethod
    def from_environment(cls) -> "ProviderConfig":
        shared_key = _read_key("DATA_GO_KR_SERVICE_KEY")
        return cls(
            data_go_kr=shared_key,
            tour_api=_read_key("TOUR_API_KEY", shared_key),
            kma=_read_key("KMA_API_KEY", shared_key),
            khoa=_read_key("KHOA_API_KEY", shared_key),
            moe=_read_key("MOE_API_KEY", shared_key),
        )

    def public_status(self) -> dict[str, bool]:
        """Return booleans only so health checks cannot leak credential material."""

        return {
            "tour_api": bool(self.tour_api),
            "weather": bool(self.kma),
            "marine": bool(self.khoa),
            "water_quality": bool(self.moe),
        }


def get_provider_status() -> dict[str, bool]:
    return ProviderConfig.from_environment().public_status()
