"""Infrastructure adapter for checking file usage in active tasks."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text as sa_text

from src.interfaces.database import Database


class FileUsageAdapter:
    """Checks whether a file is referenced by any active task.

    Queries the tasks table for rows whose ``constraints->'file_references'``
    JSONB array contains the given file ID.
    """

    async def check_file_usage(
        self,
        organization_id: str,
        file_id: str,
    ) -> Dict[str, Any]:
        db = Database()
        await db.connect()
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    sa_text(
                        "SELECT id, goal, status FROM tasks"
                        " WHERE organization_id = :org_id"
                        "   AND status IN ('planning', 'ready', 'executing', 'checkpoint')"
                        "   AND constraints::jsonb -> 'file_references' @> :ref_json ::jsonb"
                        " LIMIT 10"
                    ),
                    {
                        "org_id": organization_id,
                        "ref_json": f'[{{"id": "{file_id}"}}]',
                    },
                )
                rows = result.fetchall()
                tasks = [
                    {"id": str(r[0]), "goal": r[1], "status": r[2]}
                    for r in rows
                ]
                return {"in_use": len(tasks) > 0, "tasks": tasks}
        finally:
            await db.disconnect()
