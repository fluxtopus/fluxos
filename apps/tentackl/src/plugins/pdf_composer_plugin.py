"""
PDF Composer Plugin - Deterministic markdown to PDF conversion.

This plugin converts markdown content to professionally styled PDF documents
using the pipeline: Markdown → HTML (with CSS styling) → PDF (via Playwright).

This is a deterministic plugin (not LLM-powered) because the conversion
is a pure function with no AI reasoning involved.

Usage:
    result = await pdf_composer_handler({
        "content": "# My Report\n\nThis is the content...",
        "title": "Strategy Report",
        "document_type": "report",
        "output_path": "/tmp/report.pdf"
    })
"""

import base64
import re
import structlog
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = structlog.get_logger(__name__)


def _markdown_to_html(markdown_content: str, title: str, document_type: str) -> str:
    """Convert markdown to styled HTML document."""
    html_content = markdown_content

    # Convert headers
    html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
    html_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)

    # Convert bold and italic
    html_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_content)
    html_content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html_content)

    # Convert bullet lists
    lines = html_content.split('\n')
    in_list = False
    new_lines = []
    for line in lines:
        if line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list:
                new_lines.append('<ul>')
                in_list = True
            item = line.strip()[2:]
            new_lines.append(f'<li>{item}</li>')
        else:
            if in_list:
                new_lines.append('</ul>')
                in_list = False
            # Convert paragraphs
            if line.strip() and not line.strip().startswith('<'):
                new_lines.append(f'<p>{line}</p>')
            else:
                new_lines.append(line)
    if in_list:
        new_lines.append('</ul>')

    html_content = '\n'.join(new_lines)

    # Professional CSS styling
    css = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1a1a1a;
            padding: 60px 80px;
            max-width: 800px;
            margin: 0 auto;
        }

        .header {
            border-bottom: 3px solid #2563eb;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }

        .document-type {
            font-size: 10pt;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #2563eb;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .title {
            font-size: 28pt;
            font-weight: 700;
            color: #111827;
            margin-bottom: 10px;
        }

        .date {
            font-size: 10pt;
            color: #6b7280;
        }

        h1 {
            font-size: 20pt;
            font-weight: 700;
            color: #111827;
            margin-top: 35px;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e7eb;
        }

        h2 {
            font-size: 16pt;
            font-weight: 600;
            color: #1f2937;
            margin-top: 28px;
            margin-bottom: 12px;
        }

        h3 {
            font-size: 13pt;
            font-weight: 600;
            color: #374151;
            margin-top: 22px;
            margin-bottom: 10px;
        }

        p {
            margin-bottom: 12px;
            text-align: justify;
        }

        ul, ol {
            margin-left: 25px;
            margin-bottom: 15px;
        }

        li { margin-bottom: 6px; }
        strong { font-weight: 600; color: #111827; }
        em { font-style: italic; }
        .content { margin-top: 20px; }

        @page { margin: 0; size: A4; }
    </style>
    """

    current_date = datetime.now().strftime("%B %d, %Y")

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        {css}
    </head>
    <body>
        <div class="header">
            <div class="document-type">{document_type.upper()}</div>
            <div class="title">{title}</div>
            <div class="date">Generated on {current_date}</div>
        </div>
        <div class="content">
            {html_content}
        </div>
    </body>
    </html>
    """


async def pdf_composer_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Convert markdown content to a professionally styled PDF.

    Inputs:
        content: string (required) - Markdown content to convert
        title: string (optional) - Document title (default: "Document")
        document_type: string (optional) - Type: report, article, whitepaper, proposal, brief (default: "report")
        output_path: string (optional) - Output file path (default: "/tmp/output.pdf")

    Returns:
        {
            pdf_base64: string - Base64 encoded PDF data,
            file_path: string - Path where PDF was saved,
            size_bytes: int - Size of the PDF in bytes,
            content_type: string - "application/pdf"
        }
    """
    content = inputs.get("content", "")
    title = inputs.get("title", "Document")
    document_type = inputs.get("document_type", "report")
    output_path = inputs.get("output_path", "/tmp/output.pdf")

    if not content:
        return {
            "error": "Required field 'content' is missing",
            "pdf_base64": "",
            "file_path": "",
            "size_bytes": 0,
        }

    try:
        # Step 1: Convert markdown to styled HTML
        logger.info("pdf_composer_converting_markdown", title=title, document_type=document_type)
        html_content = _markdown_to_html(content, title, document_type)

        # Step 2: Convert HTML to PDF using Playwright
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Set HTML content
            await page.set_content(html_content)

            # Wait for fonts to load and rendering to complete
            await page.wait_for_timeout(500)

            # Generate PDF
            pdf_bytes = await page.pdf(format="A4")

            await browser.close()

        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        # Build result with PDF data
        result = {
            "pdf_base64": pdf_base64,
            "size_bytes": len(pdf_bytes),
            "content_type": "application/pdf",
            "title": title,
            "document_type": document_type,
        }

        # Auto-upload to Den if context provides org_id
        org_id = None
        workflow_id = None
        agent_id = None

        if context:
            org_id = getattr(context, "org_id", None) or getattr(context, "organization_id", None)
            workflow_id = getattr(context, "workflow_id", None)
            agent_id = getattr(context, "agent_id", None)

        if not org_id:
            org_id = inputs.get("org_id")
        if not workflow_id:
            workflow_id = inputs.get("workflow_id", "pdf-composer")
        if not agent_id:
            agent_id = inputs.get("agent_id", "pdf-composer")

        if org_id:
            try:
                from .den_file_plugin import upload_file_handler

                # Generate a filename from the title
                safe_title = title.lower().replace(" ", "-")
                safe_title = "".join(c for c in safe_title if c.isalnum() or c in "-_")
                filename = inputs.get("filename", f"{safe_title}.pdf")
                if not filename.endswith(".pdf"):
                    filename += ".pdf"

                upload_result = await upload_file_handler({
                    "org_id": org_id,
                    "workflow_id": workflow_id,
                    "agent_id": agent_id,
                    "content": pdf_base64,
                    "filename": filename,
                    "content_type": "application/pdf",
                    "is_base64": True,
                    "folder_path": inputs.get("folder_path", "/agent-outputs"),
                    "tags": inputs.get("tags", ["document", "pdf"]),
                    "is_public": inputs.get("is_public", False),
                }, context)

                if upload_result and not upload_result.get("error"):
                    result["file_id"] = upload_result.get("file_id", "")
                    result["filename"] = upload_result.get("filename", filename)
                    result["url"] = upload_result.get("url", "")
                    result["cdn_url"] = upload_result.get("cdn_url", "")
                    logger.info(
                        "pdf_composer_uploaded_to_den",
                        file_id=result["file_id"],
                        filename=result["filename"],
                    )
                else:
                    logger.warning(
                        "pdf_composer_den_upload_failed",
                        error=upload_result.get("error"),
                    )
            except Exception as den_err:
                logger.warning("pdf_composer_den_upload_error", error=str(den_err))

        # Also save locally as fallback
        file_path = Path(output_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(pdf_bytes)
        result["file_path"] = str(file_path)

        logger.info(
            "pdf_composer_success",
            file_path=str(file_path),
            size_bytes=len(pdf_bytes),
            title=title,
        )

        return result

    except Exception as e:
        logger.error("pdf_composer_failed", error=str(e))
        return {
            "error": f"PDF generation failed: {str(e)}",
            "pdf_base64": "",
            "file_path": "",
            "size_bytes": 0,
        }


# Plugin definition for registration
PLUGIN_DEFINITION = {
    "name": "pdf_composer",
    "description": "Convert markdown content to professionally styled PDF documents",
    "handler": pdf_composer_handler,
    "inputs_schema": {
        "content": {"type": "string", "required": True, "description": "Markdown content to convert to PDF"},
        "title": {"type": "string", "required": False, "default": "Document", "description": "Document title"},
        "document_type": {
            "type": "string",
            "required": False,
            "default": "report",
            "enum": ["report", "article", "whitepaper", "proposal", "brief"],
            "description": "Type of document",
        },
        "output_path": {"type": "string", "required": False, "default": "/tmp/output.pdf", "description": "Output file path"},
    },
    "outputs_schema": {
        "pdf_base64": {"type": "string", "description": "Base64 encoded PDF data"},
        "file_path": {"type": "string", "description": "Path where PDF was saved"},
        "size_bytes": {"type": "integer", "description": "Size of the PDF in bytes"},
        "content_type": {"type": "string", "description": "MIME type (application/pdf)"},
    },
    "category": "document",
}
