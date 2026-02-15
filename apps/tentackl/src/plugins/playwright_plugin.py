"""Playwright plugin for web automation and screenshot generation.

This plugin provides browser automation capabilities including:
- Screenshot generation for social media posts
- Web page rendering
- PDF generation
- HTML to image conversion
"""

from typing import Any, Dict
import asyncio
import base64
from pathlib import Path
from playwright.async_api import async_playwright


async def generate_tweet_image_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an image for a tweet using Playwright.

    Creates a visually appealing image with the tweet text and optional
    background styling. Perfect for social media content.

    Inputs:
      tweet_text: string (required) - The tweet text to render
      image_prompt: string (optional) - Description of desired visual style
      width: int (optional) - Image width in pixels (default: 1200)
      height: int (optional) - Image height in pixels (default: 630)
      background_color: string (optional) - CSS color value (default: "#1DA1F2")
      text_color: string (optional) - CSS color value (default: "white")
      font_size: int (optional) - Font size in pixels (default: 48)
      output_path: string (optional) - Where to save the image

    Returns:
      {
        result: string - Base64 encoded PNG image data,
        file_path: string - Path to saved file (if output_path provided),
        width: int,
        height: int,
        size_bytes: int
      }
    """
    tweet_text = inputs.get("tweet_text", "")
    image_prompt = inputs.get("image_prompt", "")
    width = inputs.get("width", 1200)
    height = inputs.get("height", 630)
    bg_color = inputs.get("background_color", "#1DA1F2")
    text_color = inputs.get("text_color", "white")
    font_size = inputs.get("font_size", 48)
    output_path = inputs.get("output_path", None)

    if not tweet_text:
        return {"result": "", "error": "No tweet_text provided"}

    # Create HTML template for the tweet image
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                width: {width}px;
                height: {height}px;
                background: {bg_color};
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            .tweet-container {{
                max-width: {width - 200}px;
                padding: 60px;
                text-align: center;
            }}
            .tweet-text {{
                color: {text_color};
                font-size: {font_size}px;
                line-height: 1.4;
                font-weight: 600;
                margin-bottom: 30px;
            }}
            .tweet-meta {{
                color: {text_color};
                opacity: 0.7;
                font-size: {font_size // 2}px;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="tweet-container">
            <div class="tweet-text">{tweet_text}</div>
            {f'<div class="tweet-meta">{image_prompt}</div>' if image_prompt else ''}
        </div>
    </body>
    </html>
    """

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": width, "height": height})

            # Set the HTML content
            await page.set_content(html_content)

            # Wait for fonts to load
            await page.wait_for_timeout(500)

            # Take screenshot
            screenshot_bytes = await page.screenshot(type="png", full_page=False)

            await browser.close()

        # Encode to base64 for storage/transmission
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')

        result = {
            "result": base64_image,
            "width": width,
            "height": height,
            "size_bytes": len(screenshot_bytes),
            "format": "png"
        }

        # Optionally save to file
        if output_path:
            file_path = Path(output_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(screenshot_bytes)
            result["file_path"] = str(file_path)

        return result

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to generate image: {str(e)}"
        }


async def screenshot_url_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Take a screenshot of a URL.

    Inputs:
      url: string (required) - The URL to screenshot
      width: int (optional) - Viewport width (default: 1920)
      height: int (optional) - Viewport height (default: 1080)
      full_page: bool (optional) - Capture full scrollable page (default: False)
      output_path: string (optional) - Where to save the screenshot
      wait_for_selector: string (optional) - CSS selector to wait for before screenshot

    Returns:
      {
        result: string - Base64 encoded PNG image,
        file_path: string - Path to saved file (if output_path provided),
        url: string,
        size_bytes: int
      }
    """
    url = inputs.get("url", "")
    width = inputs.get("width", 1920)
    height = inputs.get("height", 1080)
    full_page = inputs.get("full_page", False)
    output_path = inputs.get("output_path", None)
    wait_for_selector = inputs.get("wait_for_selector", None)

    if not url:
        return {"result": "", "error": "No url provided"}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": width, "height": height})

            # Navigate to URL
            await page.goto(url, wait_until="networkidle")

            # Wait for specific selector if provided
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=10000)

            # Take screenshot
            screenshot_bytes = await page.screenshot(
                type="png",
                full_page=full_page
            )

            await browser.close()

        # Encode to base64
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')

        result = {
            "result": base64_image,
            "url": url,
            "size_bytes": len(screenshot_bytes),
            "format": "png"
        }

        # Optionally save to file
        if output_path:
            file_path = Path(output_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(screenshot_bytes)
            result["file_path"] = str(file_path)

        return result

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to screenshot URL: {str(e)}"
        }


async def html_to_pdf_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Convert HTML content to PDF.

    Inputs:
      html: string (required) - HTML content to convert
      output_path: string (required) - Where to save the PDF
      format: string (optional) - Page format (A4, Letter, etc.) (default: "A4")

    Returns:
      {
        result: string - Base64 encoded PDF data,
        file_path: string,
        size_bytes: int
      }
    """
    html = inputs.get("html", "")
    output_path = inputs.get("output_path", "")
    page_format = inputs.get("format", "A4")

    if not html:
        return {"result": "", "error": "No html provided"}
    if not output_path:
        return {"result": "", "error": "No output_path provided"}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Set HTML content
            await page.set_content(html)

            # Wait for rendering
            await page.wait_for_timeout(500)

            # Generate PDF
            pdf_bytes = await page.pdf(format=page_format)

            await browser.close()

        # Save to file
        file_path = Path(output_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(pdf_bytes)

        # Encode to base64
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            "result": base64_pdf,
            "file_path": str(file_path),
            "size_bytes": len(pdf_bytes),
            "format": "pdf"
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to generate PDF: {str(e)}"
        }


# Export plugin handlers
PLUGIN_HANDLERS = {
    "generate_tweet_image": generate_tweet_image_handler,
    "screenshot_url": screenshot_url_handler,
    "html_to_pdf": html_to_pdf_handler,
}
