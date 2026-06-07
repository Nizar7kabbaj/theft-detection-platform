from pydantic import BaseModel, ConfigDict, Field, field_validator


class Bbox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class Keypoint(BaseModel):
    name: str
    x: float
    y: float
    confidence: float = Field(ge=0.0, le=1.0)


class MongoModel(BaseModel):
    """response model base, mongo _id becomes a string id"""

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", mode="before", check_fields=False)
    @classmethod
    def _stringify_id(cls, v: object) -> object:
        return str(v) if v is not None else v
