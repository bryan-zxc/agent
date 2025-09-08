"""
Unit tests for the read_image MCP tool.

These tests mock only the LLM service to avoid API costs while testing the full
orchestration logic of the read_image tool.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from pathlib import Path
import base64
from PIL import Image
import io

from agent.utils.tools import read_image
from agent.models.schemas import ImageBreakdown, ImageElement


def create_test_image():
    """Create a simple test image and return its base64 encoding."""
    img = Image.new('RGB', (100, 100), color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


@pytest.mark.asyncio
async def test_read_image_with_chart_only():
    """Test tool with image containing only chart elements."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_chart_readings_from_image') as mock_chart:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with chart element
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Sales chart for Q1",
                    element_location="center",
                    element_type="chart",
                    required=True
                )
            ]
        )
        
        # Mock chart extraction
        mock_chart.return_value = "Q: What were Q1 sales?\nA: $1.2M\nQ: What was the growth rate?\nA: 15%"
        
        # Execute
        result = await read_image.fn(image_path="/path/to/chart.png")
        
        # Verify
        assert "Chart Data:" in result
        assert "Q: What were Q1 sales?" in result
        assert "$1.2M" in result
        assert "Text, Form, and Table Data:" not in result
        assert "Diagram (Mermaid):" not in result
        
        # Verify chart extraction was called
        mock_chart.assert_called_once()
        # LLM should not be called for diagram/other extraction
        mock_llm.get_response.assert_not_called()


@pytest.mark.asyncio
async def test_read_image_with_table_only():
    """Test tool with image containing only table elements."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_text_and_table_json_from_image') as mock_text_table:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with table element
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Product inventory table",
                    element_location="top",
                    element_type="table",
                    required=True
                )
            ]
        )
        
        # Mock table extraction
        mock_text_table.return_value = '{"tables": [{"headers": ["Product", "Stock"], "rows": [["Widget", "100"]]}]}'
        
        # Execute
        result = await read_image.fn(image_path="/path/to/table.png")
        
        # Verify
        assert "Text, Form, and Table Data:" in result
        assert "Product" in result
        assert "Widget" in result
        assert "Chart Data:" not in result
        assert "Diagram (Mermaid):" not in result
        
        # Verify table extraction was called
        mock_text_table.assert_called_once()


@pytest.mark.asyncio
async def test_read_image_with_form_only():
    """Test tool with image containing only form elements."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_text_and_table_json_from_image') as mock_text_table:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with form element
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Application form",
                    element_location="full page",
                    element_type="form",
                    required=True
                )
            ]
        )
        
        # Mock form extraction
        mock_text_table.return_value = '{"forms": [{"fields": ["Name", "Email", "Phone"]}]}'
        
        # Execute
        result = await read_image.fn(image_path="/path/to/form.png")
        
        # Verify
        assert "Text, Form, and Table Data:" in result
        assert "Name" in result
        assert "Email" in result
        assert "Chart Data:" not in result
        
        # Verify form extraction was called (uses same function as tables/text)
        mock_text_table.assert_called_once()


@pytest.mark.asyncio
async def test_read_image_with_diagram_only():
    """Test tool with image containing only diagram elements."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown:
        
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "```mermaid\ngraph TD\n  A[Start] --> B[Process]\n  B --> C[End]\n```"
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with diagram element
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Process flow diagram",
                    element_location="center",
                    element_type="diagram",
                    required=True
                )
            ]
        )
        
        # Execute
        result = await read_image.fn(image_path="/path/to/diagram.png")
        
        # Verify
        assert "Diagram (Mermaid):" in result
        assert "graph TD" in result
        assert "Start" in result
        assert "Chart Data:" not in result
        assert "Text, Form, and Table Data:" not in result
        
        # Verify LLM was called for diagram extraction
        mock_llm.get_response.assert_called_once()
        call_args = mock_llm.get_response.call_args
        assert "mermaid code" in str(call_args).lower()


@pytest.mark.asyncio
async def test_read_image_with_other_content():
    """Test tool with image containing 'other' content type."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown:
        
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "This image contains a photograph of a sunset over mountains."
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with other element
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Photograph of landscape",
                    element_location="full image",
                    element_type="other",
                    required=True
                )
            ]
        )
        
        # Execute
        result = await read_image.fn(image_path="/path/to/photo.png")
        
        # Verify
        assert "Other Content:" in result
        assert "sunset over mountains" in result
        assert "Chart Data:" not in result
        
        # Verify LLM was called for other content extraction
        mock_llm.get_response.assert_called_once()
        call_args = mock_llm.get_response.call_args
        assert "non-text, non-table, non-chart" in str(call_args)


@pytest.mark.asyncio
async def test_read_image_with_multiple_types():
    """Test tool with image containing multiple content types."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_chart_readings_from_image') as mock_chart, \
         patch('agent.utils.tools.get_text_and_table_json_from_image') as mock_text_table:
        
        # Mock LLM instance
        mock_llm = MagicMock()
        mock_llm.get_response.return_value = "```mermaid\ngraph LR\n  A --> B\n```"
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with multiple element types
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Revenue chart",
                    element_location="top left",
                    element_type="chart",
                    required=True
                ),
                ImageElement(
                    element_desc="Data table",
                    element_location="bottom",
                    element_type="table",
                    required=True
                ),
                ImageElement(
                    element_desc="Process diagram",
                    element_location="right",
                    element_type="diagram",
                    required=True
                )
            ]
        )
        
        # Mock extraction functions
        mock_chart.return_value = "Q: Revenue?\nA: $5M"
        mock_text_table.return_value = '{"tables": [{"data": "sample"}]}'
        
        # Execute
        result = await read_image.fn(image_path="/path/to/complex.png")
        
        # Verify all sections are present
        assert "Chart Data:" in result
        assert "Q: Revenue?" in result
        assert "Text, Form, and Table Data:" in result
        assert '{"tables"' in result
        assert "Diagram (Mermaid):" in result
        assert "graph LR" in result
        
        # Verify sections are separated
        assert "---" in result
        
        # Verify all extractors were called
        mock_chart.assert_called_once()
        mock_text_table.assert_called_once()
        mock_llm.get_response.assert_called_once()  # For diagram


@pytest.mark.asyncio
async def test_read_image_with_table_form_text_combined():
    """Test that tables, forms, and text are extracted together in one call."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_text_and_table_json_from_image') as mock_text_table:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with table, form, and text elements
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Data table",
                    element_location="top",
                    element_type="table",
                    required=True
                ),
                ImageElement(
                    element_desc="Registration form",
                    element_location="middle",
                    element_type="form",
                    required=True
                ),
                ImageElement(
                    element_desc="Instructions text",
                    element_location="bottom",
                    element_type="text",
                    required=True
                )
            ]
        )
        
        # Mock combined extraction
        mock_text_table.return_value = '{"tables": [{"headers": ["Col1"]}], "forms": [{"fields": ["Name"]}], "text": ["Instructions here"]}'
        
        # Execute
        result = await read_image.fn(image_path="/path/to/mixed.png")
        
        # Verify combined extraction
        assert "Text, Form, and Table Data:" in result
        assert "Col1" in result
        assert "Name" in result
        assert "Instructions here" in result
        
        # Verify only called once despite multiple element types
        mock_text_table.assert_called_once()


@pytest.mark.asyncio
async def test_read_image_invalid_path():
    """Test tool with non-existent file path."""
    with patch('agent.utils.tools.is_image', return_value=(False, "File not found")):
        result = await read_image.fn(image_path="/nonexistent/path.png")
        
        assert "Error reading image: File not found" in result


@pytest.mark.asyncio
async def test_read_image_not_an_image():
    """Test tool with file that exists but isn't an image."""
    with patch('agent.utils.tools.is_image', return_value=(False, "Not a valid image file")):
        result = await read_image.fn(image_path="/path/to/document.txt")
        
        assert "Error reading image: Not a valid image file" in result


@pytest.mark.asyncio
async def test_read_image_unreadable():
    """Test tool with image marked as unreadable by breakdown."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock unreadable image
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=True,
            image_quality="Image is too blurry to extract content",
            elements=[]
        )
        
        # Execute
        result = await read_image.fn(image_path="/path/to/blurry.png")
        
        # Verify
        assert "Image cannot be analysed: Image is too blurry to extract content" in result


@pytest.mark.asyncio
async def test_read_image_no_content():
    """Test tool with valid image but no recognisable elements."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with no elements
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[]
        )
        
        # Execute
        result = await read_image.fn(image_path="/path/to/blank.png")
        
        # Verify
        assert "No recognisable content found in image" in result


@pytest.mark.asyncio
async def test_read_image_duplicate_element_types():
    """Test that duplicate element types are handled correctly (only processed once)."""
    with patch('agent.utils.tools.LLM') as mock_llm_class, \
         patch('agent.utils.tools.is_image', return_value=(True, None)), \
         patch('agent.utils.tools.encode_image', return_value=create_test_image()), \
         patch('agent.utils.tools.get_img_breakdown') as mock_breakdown, \
         patch('agent.utils.tools.get_chart_readings_from_image') as mock_chart:
        
        # Mock LLM instance
        mock_llm = AsyncMock()
        mock_llm_class.return_value = mock_llm
        
        # Mock breakdown with multiple charts (duplicate type)
        mock_breakdown.return_value = ImageBreakdown(
            unreadable=False,
            image_quality="",
            elements=[
                ImageElement(
                    element_desc="Revenue chart",
                    element_location="top",
                    element_type="chart",
                    required=True
                ),
                ImageElement(
                    element_desc="Profit chart",
                    element_location="bottom",
                    element_type="chart",
                    required=True
                ),
                ImageElement(
                    element_desc="Growth chart",
                    element_location="right",
                    element_type="chart",
                    required=True
                )
            ]
        )
        
        # Mock chart extraction
        mock_chart.return_value = "Q: Revenue?\nA: $5M\nQ: Profit?\nA: $1M\nQ: Growth?\nA: 20%"
        
        # Execute
        result = await read_image.fn(image_path="/path/to/charts.png")
        
        # Verify chart extraction was called only once despite multiple chart elements
        mock_chart.assert_called_once()
        
        # Verify all chart data is included
        assert "Revenue" in result
        assert "Profit" in result
        assert "Growth" in result