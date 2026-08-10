from pydantic import BaseModel, ConfigDict, Field, field_validator


class Bbox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class Keypoint(BaseModel):
    name: str | None = None
    x: float
    y: float
    confidence: float = Field(ge=0.0, le=1.0)


class MongoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before", check_fields=False)
    @classmethod
    def _stringify_id(cls, v: object) -> object:
        return str(v) if v is not None else v
