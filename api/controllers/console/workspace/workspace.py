import logging

from flask import request
from flask_login import current_user
from flask_restful import Resource, fields, inputs, marshal, marshal_with, reqparse
from sqlalchemy import select
from werkzeug.exceptions import Unauthorized

import services
from controllers.common.errors import FilenameNotExistsError
from controllers.console import api
from controllers.console.admin import admin_required
from controllers.console.datasets.error import (
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.console.error import AccountNotLinkTenantError
from controllers.console.wraps import (
    account_initialization_required,
    cloud_edition_billing_resource_check,
    setup_required,
)
from extensions.ext_database import db
from libs.helper import TimestampField
from libs.login import login_required
from models.account import Tenant, TenantAccountJoin, TenantStatus
from services.account_service import TenantService
from services.feature_service import FeatureService
from services.file_service import FileService
from services.workspace_service import WorkspaceService

provider_fields = {
    "provider_name": fields.String,
    "provider_type": fields.String,
    "is_valid": fields.Boolean,
    "token_is_set": fields.Boolean,
}

tenant_fields = {
    "id": fields.String,
    "name": fields.String,
    "plan": fields.String,
    "status": fields.String,
    "created_at": TimestampField,
    "role": fields.String,
    "in_trial": fields.Boolean,
    "trial_end_reason": fields.String,
    "custom_config": fields.Raw(attribute="custom_config"),
}

tenants_fields = {
    "id": fields.String,
    "name": fields.String,
    "plan": fields.String,
    "status": fields.String,
    "created_at": TimestampField,
    "current": fields.Boolean,
    "role": fields.String,
}

workspace_fields = {"id": fields.String, "name": fields.String, "status": fields.String, "created_at": TimestampField}


class TenantListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        tenants = TenantService.get_join_tenants(current_user)
        tenant_dicts = []

        for tenant in tenants:
            features = FeatureService.get_features(tenant.id)
            # 获取用户在该工作空间的角色
            join = db.session.query(TenantAccountJoin).filter(
                TenantAccountJoin.tenant_id == tenant.id,
                TenantAccountJoin.account_id == current_user.id
            ).first()

            # Create a dictionary with tenant attributes
            tenant_dict = {
                "id": tenant.id,
                "name": tenant.name,
                "status": tenant.status,
                "created_at": tenant.created_at,
                "plan": features.billing.subscription.plan if features.billing.enabled else "sandbox",
                "current": tenant.id == current_user.current_tenant_id,
                "role": join.role if join else 'unknown'
            }

            tenant_dicts.append(tenant_dict)

        return {"workspaces": marshal(tenant_dicts, tenants_fields)}, 200


class WorkspaceListApi(Resource):
    @setup_required
    @admin_required
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("page", type=inputs.int_range(1, 99999), required=False, default=1, location="args")
        parser.add_argument("limit", type=inputs.int_range(1, 100), required=False, default=20, location="args")
        args = parser.parse_args()

        stmt = select(Tenant).order_by(Tenant.created_at.desc())
        tenants = db.paginate(select=stmt, page=args["page"], per_page=args["limit"], error_out=False)
        has_more = False

        if tenants.has_next:
            has_more = True

        return {
            "data": marshal(tenants.items, workspace_fields),
            "has_more": has_more,
            "limit": args["limit"],
            "page": args["page"],
            "total": tenants.total,
        }, 200


class TenantApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(tenant_fields)
    def get(self):
        if request.path == "/info":
            logging.warning("Deprecated URL /info was used.")

        tenant = current_user.current_tenant

        if tenant.status == TenantStatus.ARCHIVE:
            tenants = TenantService.get_join_tenants(current_user)
            # if there is any tenant, switch to the first one
            if len(tenants) > 0:
                TenantService.switch_tenant(current_user, tenants[0].id)
                tenant = tenants[0]
            # else, raise Unauthorized
            else:
                raise Unauthorized("workspace is archived")

        return WorkspaceService.get_tenant_info(tenant), 200


class SwitchWorkspaceApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("tenant_id", type=str, required=True, location="json")
        args = parser.parse_args()

        # check if tenant_id is valid, 403 if not
        try:
            TenantService.switch_tenant(current_user, args["tenant_id"])
        except Exception:
            raise AccountNotLinkTenantError("Account not link tenant")

        new_tenant = db.session.query(Tenant).get(args["tenant_id"])  # Get new tenant
        if new_tenant is None:
            raise ValueError("Tenant not found")

        return {"result": "success", "new_tenant": marshal(WorkspaceService.get_tenant_info(new_tenant), tenant_fields)}


class CustomConfigWorkspaceApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check("workspace_custom")
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("remove_webapp_brand", type=bool, location="json")
        parser.add_argument("replace_webapp_logo", type=str, location="json")
        args = parser.parse_args()

        tenant = db.get_or_404(Tenant, current_user.current_tenant_id)

        custom_config_dict = {
            "remove_webapp_brand": args["remove_webapp_brand"],
            "replace_webapp_logo": args["replace_webapp_logo"]
            if args["replace_webapp_logo"] is not None
            else tenant.custom_config_dict.get("replace_webapp_logo"),
        }

        tenant.custom_config_dict = custom_config_dict
        db.session.commit()

        return {"result": "success", "tenant": marshal(WorkspaceService.get_tenant_info(tenant), tenant_fields)}


class WebappLogoWorkspaceApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @cloud_edition_billing_resource_check("workspace_custom")
    def post(self):
        # get file from request
        file = request.files["file"]

        # check file
        if "file" not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        if not file.filename:
            raise FilenameNotExistsError

        extension = file.filename.split(".")[-1]
        if extension.lower() not in {"svg", "png"}:
            raise UnsupportedFileTypeError()

        try:
            upload_file = FileService.upload_file(
                filename=file.filename,
                content=file.read(),
                mimetype=file.mimetype,
                user=current_user,
            )

        except services.errors.file.FileTooLargeError as file_too_large_error:
            raise FileTooLargeError(file_too_large_error.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return {"id": upload_file.id}, 201


class WorkspaceInfoApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    # Change workspace name
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True, location="json")
        args = parser.parse_args()

        tenant = db.get_or_404(Tenant, current_user.current_tenant_id)
        tenant.name = args["name"]
        db.session.commit()

        return {"result": "success", "tenant": marshal(WorkspaceService.get_tenant_info(tenant), tenant_fields)}

class WorkspaceCreateApi(Resource):
    @login_required
    @account_initialization_required
    def post(self):
        """创建新的工作空间"""
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True, location='json')
        args = parser.parse_args()

        try:
            # 创建新工作空间
            tenant = TenantService.create_tenant(name=args['name'])
            # 添加当前用户为工作空间拥有者
            TenantService.create_tenant_member(tenant, current_user, role="owner")

            # 返回创建的工作空间信息
            return {
                'id': tenant.id,
                'name': tenant.name,
                'role': 'owner',
                'status': tenant.status,
                'created_at': tenant.created_at.isoformat()
            }, 201
        except ValueError as e:
            return {'error': str(e)}, 400
        except Exception as e:
            if 'exceed_max_workspaces' in str(e):
                return {'error': 'exceed the maximum number of workspaces', 'code': str(e)}, 500
            logging.exception("create workspace failed")
            return {'error': 'create workspace failed'}, 500


class WorkspaceSwitchApi(Resource):
    @login_required
    @account_initialization_required
    def post(self, workspace_id):
        """switch workspace"""
        try:
            # 切换当前工作空间
            TenantService.switch_tenant(current_user, workspace_id)
            return {'message': 'switch workspace success'}, 200
        except Exception as e:
            logging.exception("switch workspace failed")
            return {'error': 'switch workspace failed'}, 500


class WorkspaceDeleteApi(Resource):
    @login_required
    @account_initialization_required
    def post(self):
        """删除工作空间"""
        parser = reqparse.RequestParser()
        parser.add_argument('workspace_id', type=str, required=True, location='json')
        args = parser.parse_args()

        try:
            workspace_id = args['workspace_id']

            # 获取要删除的工作空间
            workspace = db.session.query(Tenant).filter(Tenant.id == workspace_id).first()
            if not workspace:
                return {'error': 'workspace not found'}, 404

            # 检查当前用户是否是工作空间的所有者
            join = db.session.query(TenantAccountJoin).filter(
                TenantAccountJoin.tenant_id == workspace_id,
                TenantAccountJoin.account_id == current_user.id,
                TenantAccountJoin.role == 'owner'
            ).first()

            if not join:
                return {'error': 'only the owner of the workspace can delete the workspace'}, 403

            # 不能删除当前工作空间，需要先切换到其他工作空间
            if current_user.current_tenant_id == workspace_id:
                return {'error': 'cannot delete the current workspace, please switch to another workspace first'}, 400

            # 删除工作空间
            TenantService.dissolve_tenant(workspace, current_user)

            return {'message': 'workspace deleted successfully'}, 200
        except Exception as e:
            logging.exception("delete workspace failed")
            return {'error': 'delete workspace failed'}, 500

api.add_resource(TenantListApi, "/workspaces")  # GET for getting all tenants
api.add_resource(WorkspaceListApi, "/all-workspaces")  # GET for getting all tenants
api.add_resource(TenantApi, "/workspaces/current", endpoint="workspaces_current")  # GET for getting current tenant info
api.add_resource(TenantApi, "/info", endpoint="info")  # Deprecated
api.add_resource(SwitchWorkspaceApi, "/workspaces/switch")  # POST for switching tenant
api.add_resource(CustomConfigWorkspaceApi, "/workspaces/custom-config")
api.add_resource(WebappLogoWorkspaceApi, "/workspaces/custom-config/webapp-logo/upload")
api.add_resource(WorkspaceInfoApi, "/workspaces/info")  # POST for changing workspace info
api.add_resource(WorkspaceCreateApi, '/workspaces/create')
api.add_resource(WorkspaceSwitchApi, '/workspaces/<string:workspace_id>/switch')
api.add_resource(WorkspaceDeleteApi, '/workspaces/delete')  # POST for deleting workspace
