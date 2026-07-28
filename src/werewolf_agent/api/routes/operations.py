"""Asynchronous operation status route."""

from fastapi import APIRouter

from werewolf_agent.api.dependencies import PrincipalDependency, ServicesDependency
from werewolf_agent.api.presenters import operation_response
from werewolf_agent.application import Actor
from werewolf_agent.contracts import ResourceNotFoundError
from werewolf_agent.contracts.api import OperationResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResponse,
    operation_id="operation_get",
)
def get_operation(
    operation_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> OperationResponse:
    """Return an operation only to its owner."""
    operation = services.games.operation(operation_id, Actor(user_id=principal.user_id))
    if operation is None:
        raise ResourceNotFoundError("操作が見つかりません。")
    return operation_response(operation)
