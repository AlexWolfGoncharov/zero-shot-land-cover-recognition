import os
import json
from transformers import pipeline
import datetime
from json import JSONDecoder, JSONDecodeError
from openai import OpenAI
from .response_parser import parse_and_retry

def get_prompt_text(n_clusters, legend_description=None):
    """
    Новый подробный prompt для кластеризации WorldCover (см. openai_adapter.py)
    """
    user_prompt_text = """
You are an expert remote sensing analyst specializing in land cover classification from satellite imagery. Your task is to analyze RGB satellite images and corresponding segmentation masks to identify land cover types based on the WorldCover classification system.

You will receive two images:
1. An original RGB satellite image (True Color Image, TCI).
2. A segmentation mask in grayscale, where each unique gray value corresponds to a different cluster/segment.

Here is the grayscale mask legend that maps gray values to cluster numbers:
<grayscale_mask_legend>
{legend_description}
</grayscale_mask_legend>

IMPORTANT: The colors in the segmentation mask are arbitrary and do NOT indicate the actual land cover type. Your classification must be based SOLELY on analyzing the content in the original RGB satellite image.

Your task is to classify each numbered cluster (0-{n_clusters}) in the segmentation mask according to the WorldCover land-cover categories. Follow these steps for each cluster:

1. For each cluster, first write your visual observations for the region in the original RGB image (shape, texture, context, adjacency, etc.). Only after that, select the most likely WorldCover category, specify your confidence (high/medium/low), and provide a brief reasoning (≤ 25 words).
2. Examine the area in the RGB image corresponding to the cluster.
3. Analyze visual patterns, shapes, textures, and contextual relationships.
4. List key visual features observed in the RGB image for this cluster.
5. Consider multiple possible WorldCover categories that could apply to this cluster.
6. Select the most appropriate WorldCover category based on your analysis.
7. Determine your confidence level (high, medium, or low).
8. Provide concise reasoning (≤ 25 words) citing specific visual evidence from the RGB image.

Before providing your final classification, wrap your analysis inside <cluster_analysis> tags. Analyze each cluster separately, showing your thought process for each. This will help ensure a thorough interpretation of the data and prevent reliance on mask colors.

WorldCover Categories:
- Tree cover
- Shrubland
- Grassland 
- Cropland
- Built-up
- Bare / sparse vegetation
- Snow and ice
- Permanent water bodies
- Herbaceous wetland
- Mangroves
- Moss and lichen

Output your final classification as valid JSON in the following format:

{{
  "0": {{"category": "...", "confidence": "...", "reasoning": "..."}},
  "1": {{"category": "...", "confidence": "...", "reasoning": "..."}},
  "2": {{"category": "...", "confidence": "...", "reasoning": "..."}},
  "3": {{"category": "...", "confidence": "...", "reasoning": "..."}},
  "4": {{"category": "...", "confidence": "...", "reasoning": "..."}},
  "5": {{"category": "...", "confidence": "...", "reasoning": "..."}}
}}

Remember:
- Base your decision EXCLUSIVELY on visual patterns in the RGB image.
- IGNORE ALL COLORS in the segmentation mask. The mask serves only as a region outline.
- Maintain scientific objectivity and indicate confidence levels appropriately.
- Provide thorough, precise, and scientifically accurate analysis of each segment.

Begin your analysis now, starting with cluster 0 and proceeding through cluster {n_clusters}.
"""
    return user_prompt_text.format(legend_description=legend_description or "{}", n_clusters=n_clusters)

def get_single_segment_prompt_text(legend_description=None):
    """
    Prompt для случая, когда отправляется только один сегмент (кластер) — бинарная маска.
    """
    user_prompt_text = """
You are an expert remote sensing analyst specializing in land cover classification from satellite imagery. Your task is to analyze RGB satellite images and a binary segmentation mask to identify the land cover type of a single segment based on the WorldCover classification system.

You will receive two images:
1. An original RGB satellite image (True Color Image, TCI).
2. A binary segmentation mask, where WHITE pixels (value=255) correspond to the single segment of interest (cluster 0), and BLACK pixels (value=0) are background.

IMPORTANT: The mask only shows the region to analyze. The color (white) is arbitrary and does NOT indicate the land cover type. Your classification must be based SOLELY on analyzing the content in the original RGB satellite image within the white region.

Your task is to classify ONLY the highlighted segment (cluster 0) in the mask according to the WorldCover land-cover categories. Ignore all other regions.

Follow these steps:
1. Carefully examine the area in the RGB image corresponding to the white region in the mask.
2. List your visual observations (shape, texture, context, adjacency, etc.).
3. Select the most likely WorldCover category, specify your confidence (high/medium/low), and provide a brief reasoning (≤ 25 words).

WorldCover Categories:
- Tree cover
- Shrubland
- Grassland
- Cropland
- Built-up
- Bare / sparse vegetation
- Snow and ice
- Permanent water bodies
- Herbaceous wetland
- Mangroves
- Moss and lichen

Output your final classification as valid JSON in the following format:
{{
  "0": {{"category": "...", "confidence": "...", "reasoning": "..."}}
}}

Remember:
- Base your decision EXCLUSIVELY on visual patterns in the RGB image within the white region.
- IGNORE ALL COLORS in the mask. The mask serves only as a region outline.
- Maintain scientific objectivity and indicate confidence levels appropriately.
- Provide thorough, precise, and scientifically accurate analysis of the segment.

Begin your analysis now for cluster 0 only.
"""
    return user_prompt_text.format(legend_description=legend_description or "{}")

def ibm_granite_vision_categorize(image_path, mask_path, n_clusters, legend_image_path=None, model_name=None, legend_description=None, user_prompt_text=None, **kwargs):
    """
    Категоризация кластеров через IBM Granite Vision (через transformers pipeline).
    """
    model = model_name or "ibm-granite/granite-vision-3.2-2b"
    pipe = pipeline("image-text-to-text", model=model)
    if user_prompt_text is not None:
        prompt = user_prompt_text
    else:
        prompt = get_prompt_text(n_clusters, legend_description)
    if legend_description:
        prompt += f"\n\n{legend_description}\n"
    # Формируем сообщения для pipeline
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "path": image_path},
                {"type": "image", "path": mask_path},
                {"type": "text", "text": prompt}
            ]
        }
    ]
    if legend_image_path and os.path.exists(legend_image_path):
        messages[0]["content"].append({"type": "image", "path": legend_image_path})
    # Вызов pipeline
    result = pipe(messages)
    # result обычно строка с JSON или текстом
    text = result[0]["generated_text"] if isinstance(result, list) and "generated_text" in result[0] else str(result)
    # Извлекаем JSON с fallback
    openai_api_key = get_secret("OPENAI_API_KEY")
    return parse_and_retry(text, n_clusters, "IBM_Granite", openai_api_key)
