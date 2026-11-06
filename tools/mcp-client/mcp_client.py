import os
import sys
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    # ---------------------------------------------------------
    # Read runtime values supplied by GitHub Actions
    # ---------------------------------------------------------
    mcp_url = os.environ.get("MCP_SERVER_URL")
    work_item_id = os.environ.get("WORK_ITEM_ID")
    pr_url = os.environ.get("PR_URL")

    if not mcp_url:
        raise ValueError("MCP_SERVER_URL is not configured")

    if not work_item_id:
        raise ValueError("WORK_ITEM_ID is not configured")

    if not pr_url:
        raise ValueError("PR_URL is not configured")

    try:
        work_item_id = int(work_item_id)
    except ValueError:
        raise ValueError(
            f"Invalid WORK_ITEM_ID: {work_item_id}"
        )

    print(f"Connecting to MCP server...")
    print(f"Azure DevOps Work Item: {work_item_id}")
    print(f"GitHub PR: {pr_url}")

    # ---------------------------------------------------------
    # Connect to MCP deployed on Azure Web App
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

            # -------------------------------------------------
            # Discover tools
            # -------------------------------------------------
            tools_response = await session.list_tools()

            tool_names = [tool.name for tool in tools_response.tools]

            print("Available MCP tools:")
            for tool_name in tool_names:
                print(f"  - {tool_name}")

            # -------------------------------------------------
            # IMPORTANT
            #
            # Replace these with the EXACT names returned
            # by list_tools() if your server uses other names.
            # -------------------------------------------------
            GET_WORK_ITEM_TOOL = "get_work_item"
            UPDATE_WORK_ITEM_TOOL = "update_work_item"

            if GET_WORK_ITEM_TOOL not in tool_names:
                raise RuntimeError(
                    f"MCP tool not found: {GET_WORK_ITEM_TOOL}"
                )

            if UPDATE_WORK_ITEM_TOOL not in tool_names:
                raise RuntimeError(
                    f"MCP tool not found: {UPDATE_WORK_ITEM_TOOL}"
                )

            # -------------------------------------------------
            # TOOL 1: Fetch the User Story
            # -------------------------------------------------
            print(
                f"Fetching Azure DevOps work item "
                f"{work_item_id}..."
            )

            get_result = await session.call_tool(
                GET_WORK_ITEM_TOOL,
                arguments={
                    "id": work_item_id
                }
            )

            if get_result.isError:
                raise RuntimeError(
                    f"Unable to retrieve work item "
                    f"{work_item_id}: {get_result.content}"
                )

            print(
                f"Successfully found work item "
                f"{work_item_id}"
            )

            # -------------------------------------------------
            # TOOL 2: Update User Story with PR URL
            # -------------------------------------------------

            print(
                f"Updating work item {work_item_id} "
                f"with PR URL..."
            )

            update_result = await session.call_tool(
                UPDATE_WORK_ITEM_TOOL,
                arguments={
                    "id": work_item_id,

                    # CHANGE this field according to your
                    # Update work item MCP tool schema.
                    "fields": {
                        "Custom.PullRequestUrl": pr_url
                    }
                }
            )

            if update_result.isError:
                raise RuntimeError(
                    f"Unable to update work item "
                    f"{work_item_id}: {update_result.content}"
                )

            print(
                f"Successfully updated work item "
                f"{work_item_id}"
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
