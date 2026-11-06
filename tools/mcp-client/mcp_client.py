import asyncio
import json
import os
import sys
import html

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def get_text_from_tool_result(result):
    """
    Extract text returned by an MCP tool.
    """
    if not result.content:
        return ""

    for item in result.content:
        if hasattr(item, "text"):
            return item.text

    return ""


async def main():

    # ---------------------------------------------------------
    # Runtime values coming from GitHub Actions
    # ---------------------------------------------------------
    mcp_url = os.environ.get("MCP_SERVER_URL")
    workitem_id = os.environ.get("WORK_ITEM_ID")
    pr_url = os.environ.get("PR_URL")
    pr_number = os.environ.get("PR_NUMBER", "")

    if not mcp_url:
        raise RuntimeError("MCP_SERVER_URL is missing")

    if not workitem_id:
        raise RuntimeError("WORK_ITEM_ID is missing")

    if not pr_url:
        raise RuntimeError("PR_URL is missing")

    try:
        workitem_id = int(workitem_id)
    except ValueError:
        raise RuntimeError(
            f"Invalid WORK_ITEM_ID: {workitem_id}"
        )

    print(f"Work Item ID : {workitem_id}")
    print(f"PR URL       : {pr_url}")
    print("Connecting to MCP server...")

    # ---------------------------------------------------------
    # Connect to Azure WebApp MCP server
    # ---------------------------------------------------------
    async with streamablehttp_client(mcp_url) as (
        read_stream,
        write_stream,
        _
    ):

        async with ClientSession(
            read_stream,
            write_stream
        ) as session:

            await session.initialize()

            print("Connected to MCP server")

            # =================================================
            # TOOL 1
            # get_work_item
            # =================================================

            print(
                f"Fetching User Story {workitem_id}..."
            )

            get_result = await session.call_tool(
                "get_work_item",
                arguments={
                    "workitem_id": workitem_id,
                    "expand_relations": True
                }
            )

            if get_result.isError:
                raise RuntimeError(
                    f"get_work_item failed: "
                    f"{get_result.content}"
                )

            response_text = get_text_from_tool_result(
                get_result
            )

            print(
                f"User Story {workitem_id} found."
            )

            # -------------------------------------------------
            # Parse get_work_item response
            # -------------------------------------------------

            try:
                response_json = json.loads(response_text)
            except json.JSONDecodeError:
                raise RuntimeError(
                    "get_work_item did not return valid JSON: "
                    + response_text
                )

            # Your _success() response contains work_item.
            work_item = response_json.get(
                "work_item",
                {}
            )

            fields = work_item.get(
                "fields",
                {}
            )

            existing_description = fields.get(
                "System.Description",
                ""
            ) or ""

            # -------------------------------------------------
            # Avoid adding the same PR twice
            # -------------------------------------------------

            if pr_url in existing_description:
                print(
                    "PR URL already exists in User Story. "
                    "No update required."
                )
                return

            # -------------------------------------------------
            # Build new description
            # -------------------------------------------------

            safe_pr_url = html.escape(
                pr_url,
                quote=True
            )

            if pr_number:
                link_text = (
                    f"GitHub Pull Request #{html.escape(pr_number)}"
                )
            else:
                link_text = "GitHub Pull Request"

            pr_html = (
                "<p><strong>GitHub Pull Request:</strong> "
                f'<a href="{safe_pr_url}">'
                f"{link_text}</a></p>"
            )

            if existing_description.strip():
                updated_description = (
                    existing_description
                    + "<br/>"
                    + pr_html
                )
            else:
                updated_description = pr_html

            # =================================================
            # TOOL 2
            # update_work_item
            # =================================================

            print(
                f"Updating User Story {workitem_id}..."
            )

            update_result = await session.call_tool(
                "update_work_item",
                arguments={
                    "workitem_id": workitem_id,
                    "description_html":
                        updated_description
                }
            )

            if update_result.isError:
                raise RuntimeError(
                    f"update_work_item failed: "
                    f"{update_result.content}"
                )

            print(
                f"SUCCESS: User Story {workitem_id} "
                f"updated with PR URL."
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except Exception as exc:

        print(
            f"ERROR: {exc}",
            file=sys.stderr
        )

        sys.exit(1)
