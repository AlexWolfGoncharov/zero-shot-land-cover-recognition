import os
import json
import base64
import requests
import logging
import datetime
from json import JSONDecoder, JSONDecodeError
from openai import OpenAI
from .response_parser import parse_and_retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_secret(secret_name):
    secret = os.environ.get(secret_name)
    if secret:
        return secret
    try:
        with open('secrets.json', 'r', encoding='utf-8') as f:
            secrets = json.load(f)
        return secrets.get(secret_name)
    except Exception as e:
        logger.warning(f"Не удалось прочитать секрет {secret_name}: {e}")
        return None

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_prompt_text(n_clusters, legend_description=None):
    """
    Новый подробный prompt для кластеризации WorldCover (chain-of-thought, как в других адаптерах)
    """
    user_prompt_text = """
You are an expert remote sensing analyst specializing in land cover classification from satellite imagery. Your task is to analyze RGB satellite images and corresponding segmentation masks to identify land cover types based on the WorldCover classification system.

You have received two images:
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

def _call_gemini_vision(endpoint_url, headers, payload):
    response = requests.post(endpoint_url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    result = response.json()
    try:
        text = result['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        logger.error(f"Failed to extract text from Gemini response: {e}\nResponse: {str(result)[:300]}")
        raise ValueError(f"Gemini response structure error: {e}")
    return text

def gemini_vision_categorize(image_path, mask_path, n_clusters, legend_image_path=None, model_name=None, temperature=0.2, seed=None, user_prompt_text=None, **kwargs):
    """
    Категоризация кластеров через Google Gemini Vision API. Возвращает dict по кластерам.
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or get_secret("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY должен быть задан!")
    if not model_name:
        model_name = "gemini-2.5-flash-preview-04-17"
    endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    if user_prompt_text is not None:
        prompt = user_prompt_text
    else:
        prompt = get_prompt_text(n_clusters)
    image_b64 = encode_image_to_base64(image_path)
    mask_b64 = encode_image_to_base64(mask_path)
    images = [
        {"inlineData": {"mimeType": "image/png", "data": image_b64}},
        {"inlineData": {"mimeType": "image/png", "data": mask_b64}},
    ]
    if legend_image_path and os.path.exists(legend_image_path):
        legend_b64 = encode_image_to_base64(legend_image_path)
        images.append({"inlineData": {"mimeType": "image/png", "data": legend_b64}})
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    *images
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature
        }
    }
    headers = {
        "Content-Type": "application/json"
    }
    # Первый запрос
    result_text = _call_gemini_vision(endpoint_url, headers, payload)
    logger.info(f"RAW LLM RESPONSE (1st try): {result_text}")
    parsed = _try_parse_json(result_text, n_clusters)
    if parsed is not None:
        return parsed
    # Второй запрос
    logger.warning("Первый ответ невалиден, повторяем запрос к той же модели...")
    result_text2 = _call_gemini_vision(endpoint_url, headers, payload)
    logger.info(f"RAW LLM RESPONSE (2nd try): {result_text2}")
    parsed2 = _try_parse_json(result_text2, n_clusters)
    if parsed2 is not None:
        return parsed2
    # Fallback: parse_and_retry (через OpenAI)
    logger.error("Оба ответа невалидны, пытаемся извлечь JSON через parse_and_retry...")
    openai_api_key = get_secret("OPENAI_API_KEY")
    return parse_and_retry(result_text2, n_clusters, "Gemini", openai_api_key)

def _try_parse_json(result_text, n_clusters):
    decoder = JSONDecoder()
    start_idx = result_text.find('{')
    if start_idx >= 0:
        json_text = result_text[start_idx:]
    else:
        json_text = result_text
    try:
        result, idx = decoder.raw_decode(json_text)
        bad_keys = [k for k in result.keys() if not str(k).isdigit()]
        if bad_keys:
            return None
        return result
    except Exception:
        return None
