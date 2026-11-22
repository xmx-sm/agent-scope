"""菜单路由：我的菜单与超管菜单配置。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, SuperAdmin, ok
from app.schemas import MenuCreateIn, MenuReorderIn, MenuUpdateIn
from app.services.menu import command as menu_command
from app.services.menu import query as menu_query

router = APIRouter(tags=["菜单"])


@router.get("/menus/mine")
async def my_menus(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await menu_query.async_mine({"session": db, "user": user}))


@router.get("/admin/menus")
async def list_menus(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await menu_query.async_list_all({"session": db}))


@router.post("/admin/menus")
async def create_menu(body: MenuCreateIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await menu_command.async_create_menu({"session": db, "data": body.model_dump()}), "菜单已创建")


@router.put("/admin/menus/{menu_id}")
async def update_menu(
    menu_id: str, body: MenuUpdateIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await menu_command.async_update_menu(
            {"session": db, "menu_id": menu_id, "data": body.model_dump(exclude_unset=True)}
        ),
        "菜单已更新",
    )


@router.delete("/admin/menus/{menu_id}")
async def delete_menu(menu_id: str, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    await menu_command.async_delete_menu({"session": db, "menu_id": menu_id})
    return ok(None, "菜单已删除")


@router.post("/admin/menus/reorder")
async def reorder_menus(
    body: MenuReorderIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await menu_command.async_reorder_menus({"session": db, "ids": body.ids}),
        "排序已保存",
    )
