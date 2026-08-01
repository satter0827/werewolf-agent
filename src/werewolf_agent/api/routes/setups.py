"""Game setup catalog, preview, and user revision routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status

from werewolf_agent.api.dependencies import (
    OptionalPrincipalDependency,
    OwnedSetupsDependency,
    PrincipalDependency,
    PublicSetupsDependency,
    RequestServices,
    ServicesDependency,
)
from werewolf_agent.api.presenters import saved_setup_revision_response
from werewolf_agent.application import Actor, AppError, ErrorCode, parse_setup_document
from werewolf_agent.contracts.api import (
    PlayerPreviewRequest,
    PlayerPreviewResponse,
    SavedSetupListResponse,
    SavedSetupRevisionListResponse,
    SavedSetupRevisionResponse,
    SavedSetupSummaryResponse,
    SetupCatalogResponse,
    SetupCreateRequest,
    SetupRevisionCreateRequest,
    SetupTemplateResponse,
    SetupValidationResponse,
)
from werewolf_agent.contracts.schemas import (
    GameSetupDocumentRequest,
    GameSetupSelectionRequest,
)
from werewolf_agent.security.principal import Principal

router = APIRouter(tags=["setups"])


def _actor(principal: PrincipalDependency) -> Actor:
    return Actor(
        user_id=principal.user_id,
        is_anonymous=principal.is_anonymous,
        is_admin=principal.is_admin,
    )


def _document(request: GameSetupDocumentRequest) -> Any:
    return parse_setup_document(request.model_dump(mode="json"))


def resolve_setup(
    request: GameSetupSelectionRequest,
    principal: Principal,
    services: RequestServices,
) -> Any:
    """Resolve a wire selection to one immutable complete document."""
    if request.mode == "template":
        return services.setups.template(request.template_id)
    if request.mode == "saved":
        return services.setups.get(
            _actor(principal),
            request.setup_id,
            revision=request.revision,
        ).document
    return _document(request.document)


@router.get("/setup-catalog", response_model=SetupCatalogResponse, operation_id="setup_catalog_get")
def get_catalog(setups: PublicSetupsDependency) -> SetupCatalogResponse:
    """Return public template metadata without requiring authentication."""
    return SetupCatalogResponse.model_validate(setups.catalog().model_dump(mode="json"))


@router.get(
    "/setup-templates/{template_id}",
    response_model=SetupTemplateResponse,
    operation_id="setup_template_get",
)
def get_template(template_id: str, setups: PublicSetupsDependency) -> SetupTemplateResponse:
    """Return one public complete template without requiring authentication."""
    document = setups.template(template_id)
    return SetupTemplateResponse(
        template_id=template_id,
        document=GameSetupDocumentRequest.model_validate(document.to_mapping()),
    )


@router.post(
    "/setups/validate", response_model=SetupValidationResponse, operation_id="setup_validate"
)
def validate_setup(
    request: GameSetupDocumentRequest,
    setups: PublicSetupsDependency,
) -> SetupValidationResponse:
    """Validate an inline setup without requiring authentication."""
    result = setups.validate(request.model_dump(mode="json"))
    return SetupValidationResponse.model_validate(result.model_dump(mode="json"))


@router.post(
    "/setups/preview-players",
    response_model=PlayerPreviewResponse,
    operation_id="setup_player_preview",
)
def preview_setup_players(
    request: PlayerPreviewRequest,
    principal: OptionalPrincipalDependency,
    public_setups: PublicSetupsDependency,
    owned_setups: OwnedSetupsDependency,
) -> PlayerPreviewResponse:
    """Preview template and inline setups publicly, or an authenticated saved revision."""
    if request.setup.mode == "saved":
        if principal is None or owned_setups is None:
            raise AppError(
                "保存したゲーム設定を使うにはログインしてください。",
                code=ErrorCode.AUTHENTICATION_REQUIRED,
            )
        document = owned_setups.get(
            _actor(principal), request.setup.setup_id, revision=request.setup.revision
        ).document
    elif request.setup.mode == "template":
        document = public_setups.template(request.setup.template_id)
    else:
        document = _document(request.setup.document)
    result = public_setups.preview(document, seed=request.seed)
    return PlayerPreviewResponse.model_validate(result.model_dump(mode="json"))


@router.get("/setups", response_model=SavedSetupListResponse, operation_id="setup_list")
def list_setups(
    principal: PrincipalDependency,
    services: ServicesDependency,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> SavedSetupListResponse:
    page = services.setups.list_setups(_actor(principal), limit=limit, offset=offset)
    return SavedSetupListResponse(
        items=[
            SavedSetupSummaryResponse.model_validate(item.model_dump(mode="json"))
            for item in page.items
        ],
        next_offset=page.next_offset,
    )


@router.post(
    "/setups",
    response_model=SavedSetupRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="setup_create",
)
def create_setup(
    request: SetupCreateRequest,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> SavedSetupRevisionResponse:
    result = services.setups.create(
        _actor(principal),
        display_name=request.display_name,
        document=_document(request.document),
    )
    return saved_setup_revision_response(result)


@router.get(
    "/setups/{setup_id}",
    response_model=SavedSetupRevisionResponse,
    operation_id="setup_get",
)
def get_setup(
    setup_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> SavedSetupRevisionResponse:
    result = services.setups.get(_actor(principal), setup_id)
    return saved_setup_revision_response(result)


@router.get(
    "/setups/{setup_id}/revisions",
    response_model=SavedSetupRevisionListResponse,
    operation_id="setup_revision_list",
)
def list_setup_revisions(
    setup_id: str,
    principal: PrincipalDependency,
    services: ServicesDependency,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> SavedSetupRevisionListResponse:
    page = services.setups.revisions(_actor(principal), setup_id, limit=limit, offset=offset)
    return SavedSetupRevisionListResponse(
        items=[saved_setup_revision_response(item) for item in page.items],
        next_offset=page.next_offset,
    )


@router.get(
    "/setups/{setup_id}/revisions/{revision}",
    response_model=SavedSetupRevisionResponse,
    operation_id="setup_revision_get",
)
def get_setup_revision(
    setup_id: str,
    revision: int,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> SavedSetupRevisionResponse:
    result = services.setups.get(_actor(principal), setup_id, revision=revision)
    return saved_setup_revision_response(result)


@router.post(
    "/setups/{setup_id}/revisions",
    response_model=SavedSetupRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="setup_revision_create",
)
def create_setup_revision(
    setup_id: str,
    request: SetupRevisionCreateRequest,
    principal: PrincipalDependency,
    services: ServicesDependency,
) -> SavedSetupRevisionResponse:
    result = services.setups.save_revision(
        _actor(principal),
        setup_id,
        expected_revision=request.expected_revision,
        document=_document(request.document),
    )
    return saved_setup_revision_response(result)


__all__ = ["resolve_setup", "router"]
