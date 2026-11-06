import asyncio
import html
import json
import os
import sys
import traceback

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def get_text_from_tool_result(result) -> str:
    """
    Extract the text returned from an MCP tool result.
    """

    if not result.content:
        return ""

    for item in result.content:
        if hasattr(item, "text"):
            return item.text

    return ""


async def main():

    # =========================================================
    # 1. Read values passed from GitHub Actions
    # =========================================================

    mcp_url = os.environ.get("MCP_SERVER_URL")
    workitem_id = os.environ.get("WORK_ITEM_ID")
    pr_url = os.environ.get("PR_URL")
    pr_number = os.environ.get("PR_NUMBER", "")

    # =========================================================
    # 2. Validate required configuration
    # =========================================================

    if not mcp_url:
        raise RuntimeError(
            "MCP_SERVER_URL is missing."
        )

    if not workitem_id:
        raise RuntimeError(
            "WORK_ITEM_ID is missing."
        )

    if not pr_url:
        raise RuntimeError(
            "PR_URL is missing."
        )

    try:
        workitem_id = int(workitem_id)
    except ValueError:
        raise RuntimeError(
            f"Invalid WORK_ITEM_ID: {workitem_id}"
        )

    print("========================================")
    print("GitHub -> Azure DevOps MCP Integration")
    print("========================================")

    print(f"Work Item ID : {workitem_id}")
    print(f"PR Number    : {pr_number}")
    print(f"PR URL       : {pr_url}")

    print()

    # =========================================================
    # 3. Connect to deployed MCP WebApp
    # =========================================================

    print("Connecting to MCP server...")

    async with streamable_http_client(
        mcp_url
    ) as (
        read_stream,
        write_stream
    ):

        async with ClientSession(
            read_stream,
            write_stream
        ) as session:

            # -------------------------------------------------
            # Initialize MCP session
            # -------------------------------------------------

            await session.initialize()

            print("Connected to MCP server.")

            # =================================================
            # TOOL 1: get_work_item
            # =================================================

            print()
            print(
                f"Fetching Azure DevOps User Story "
                f"{workitem_id}..."
            )

            get_result = await session.call_tool(
                "get_work_item",
                arguments={
                    "workitem_id": workitem_id,
                    "expand_relations": True
                }
            )

            # IMPORTANT:
            # Current MCP SDK uses is_error, not isError.
            if get_result.is_error:
                raise RuntimeError(
                    "get_work_item MCP call failed: "
                    f"{get_result.content}"
                )

            response_text = get_text_from_tool_result(
                get_result
            )

            if not response_text:
                raise RuntimeError(
                    "get_work_item returned an empty response."
                )

            # -------------------------------------------------
            # Parse your server's JSON response
            # -------------------------------------------------

            try:
                response_json = json.loads(
                    response_text
                )

            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "get_work_item returned invalid JSON. "
                    f"Response: {response_text}"
                ) from exc

            # -------------------------------------------------
            # Your MCP returns:
            #
            # {
            #   "success": true,
            #   "work_item": {...}
            # }
            # -------------------------------------------------

            if not response_json.get("success"):
                raise RuntimeError(
                    "Azure DevOps get_work_item failed: "
                    f"{response_text}"
                )

            work_item = response_json.get(
                "work_item"
            )

            if not isinstance(work_item, dict):
                raise RuntimeError(
                    "get_work_item response does not contain "
                    "a valid work_item object."
                )

            returned_id = work_item.get("id")

            if returned_id != workitem_id:
                raise RuntimeError(
                    "Returned Azure DevOps work-item ID "
                    f"does not match requested ID. "
                    f"Requested={workitem_id}, "
                    f"Returned={returned_id}"
                )

            # -------------------------------------------------
            # Optional validation:
            # Make sure it actually is a User Story.
            # -------------------------------------------------

            work_item_type = work_item.get(
                "type",
                ""
            )

            work_item_title = work_item.get(
                "title",
                ""
            )

            print(
                f"Work Item found: {returned_id}"
            )

            print(
                f"Type           : {work_item_type}"
            )

            print(
                f"Title          : {work_item_title}"
            )

            if (
                work_item_type
                and work_item_type.lower() != "user story"
            ):
                raise RuntimeError(
                    f"Work Item {workitem_id} is "
                    f"'{work_item_type}', not 'User Story'."
                )

            # =================================================
            # 4. Read existing description
            # =================================================
            #
            # Your server's _serialize_work_item() converts:
            #
            # System.Description
            #
            # into:
            #
            # description_html
            #
            # So DO NOT attempt:
            #
            # work_item["fields"]["System.Description"]
            #
            # =================================================

            existing_description = work_item.get(
                "description_html",
                ""
            ) or ""

            # =================================================
            # 5. Check whether this PR was already added
            # =================================================

            if pr_url in existing_description:

                print()
                print(
                    "PR URL already exists in the "
                    "User Story description."
                )

                print(
                    "No Azure DevOps update is required."
                )

                print()
                print(
                    "Integration completed successfully."
                )

                return

            # =================================================
            # 6. Safely create PR HTML
            # =================================================

            safe_pr_url = html.escape(
                pr_url,
                quote=True
            )

            safe_pr_number = html.escape(
                str(pr_number)
            )

            if pr_number:

                link_text = (
                    f"GitHub Pull Request #{safe_pr_number}"
                )

            else:

                link_text = (
                    "GitHub Pull Request"
                )

            pr_html = (
                "<p>"
                "<strong>GitHub Pull Request:</strong> "
                f'<a href="{safe_pr_url}">'
                f"{link_text}"
                "</a>"
                "</p>"
            )

            # =================================================
            # 7. Preserve existing description
            # =================================================

            if existing_description.strip():

                updated_description = (
                    existing_description
                    + "<br/>"
                    + pr_html
                )

            else:

                updated_description = pr_html

            # =================================================
            # TOOL 2: update_work_item
            # =================================================

            print()
            print(
                f"Updating Azure DevOps User Story "
                f"{workitem_id}..."
            )

            update_result = await session.call_tool(
                "update_work_item",
                arguments={
                    "workitem_id": workitem_id,
                    "description_html":
                        updated_description
                }
            )

            # IMPORTANT:
            # Current MCP SDK uses is_error.
            if update_result.is_error:

                raise RuntimeError(
                    "update_work_item MCP call failed: "
                    f"{update_result.content}"
                )

            update_response_text = (
                get_text_from_tool_result(
                    update_result
                )
            )

            if not update_response_text:

                raise RuntimeError(
                    "update_work_item returned "
                    "an empty response."
                )

            # -------------------------------------------------
            # Validate the server response
            # -------------------------------------------------

            try:

                update_response = json.loads(
                    update_response_text
                )

            except json.JSONDecodeError as exc:

                raise RuntimeError(
                    "update_work_item returned invalid JSON. "
                    f"Response: {update_response_text}"
                ) from exc

            # Your tool can return a successful MCP call
            # while the underlying Azure DevOps operation
            # returns success:false.
            #
            # Therefore BOTH levels must be checked.

            if not update_response.get("success"):

                raise RuntimeError(
                    "Azure DevOps update_work_item failed: "
                    f"{update_response_text}"
                )

            # =================================================
            # SUCCESS
            # =================================================

            print()
            print("========================================")
            print("SUCCESS")
            print("========================================")

            print(
                f"Azure DevOps User Story "
                f"{workitem_id} updated successfully."
            )

            print(
                f"GitHub PR #{pr_number} added "
                f"to the User Story description."
            )

            print(
                f"PR URL: {pr_url}"
            )

            print("========================================")


# =============================================================
# Application entry point
# =============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except BaseException as exc:

        print(
            "\n========== COMPLETE MCP ERROR ==========",
            file=sys.stderr
        )

        traceback.print_exception(
            type(exc),
            exc,
            exc.__traceback__,
            file=sys.stderr
        )

        print(
            "========================================\n",
            file=sys.stderr
        )

        sys.exit(1)
