from pydantic import BaseModel


class RolePermissionMap(BaseModel):
    permissions: list[str]
    roles: dict[str, list[str]]
