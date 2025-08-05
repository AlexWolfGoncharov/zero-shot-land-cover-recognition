import os
import json
import base64
import logging
from anthropic import Anthropic
import datetime
from json import JSONDecoder, JSONDecodeError
from openai import OpenAI
from .cost_tracker import track_api_cost

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = "claude-3-7-sonnet-20250219"

# --- Получение ключа ---
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

def get_claude_client():
    api_key = get_secret("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY не найден в окружении или secrets.json")
    return Anthropic(api_key=api_key)

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def get_prompt_text(n_clusters, legend_description=None):
    """
    Новый подробный prompt для кластеризации WorldCover (см. openai_adapter.py)
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

def _call_claude_vision(client, messages, model_name):
    response = client.messages.create(
        model=model_name,
        max_tokens=4000,
        messages=messages
    )
    
    # Отслеживаем стоимость
    try:
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        track_api_cost(
            provider="claude",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=response.id,
            additional_info={
                "model": model_name,
                "max_tokens": 4000
            }
        )
    except Exception as e:
        logger.warning(f"Не удалось отследить стоимость запроса Claude: {e}")
    
    return response.content[0].text

def claude_vision_categorize(image_path, mask_path, n_clusters, legend_image_path=None, model_name=None, legend_description=None, temperature=0.2, seed=None, user_prompt_text=None, **kwargs):
    """
    Категоризация кластеров через Claude Sonnet 3.7. Возвращает dict по кластерам.
    """
    client = get_claude_client()
    if user_prompt_text is not None:
        prompt = user_prompt_text
    else:
        prompt = get_prompt_text(n_clusters, legend_description)
    if legend_description:
        prompt += f"\n\n{legend_description}\n"
    # Кодируем изображения в base64
    image_b64 = encode_image_to_base64(image_path)
    mask_b64 = encode_image_to_base64(mask_path)
    content = [
        {"type": "text", "text": prompt},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": mask_b64}},
    ]
    if legend_image_path and os.path.exists(legend_image_path):
        legend_b64 = encode_image_to_base64(legend_image_path)
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": legend_b64}})
    messages = [
        {"role": "user", "content": content}
    ]
    logger.info(f"Отправляем запрос к Claude: {MODEL_NAME}, длина промпта: {len(prompt)}")
    model_to_use = model_name if model_name else MODEL_NAME
    # Первый запрос
    result_text = _call_claude_vision(client, messages, model_to_use)
    logger.info(f"RAW LLM RESPONSE (1st try): {result_text}")
    parsed = _try_parse_json(result_text, n_clusters)
    if parsed is not None:
        return parsed
    # Второй запрос
    logger.warning("Первый ответ невалиден, повторяем запрос к той же модели...")
    result_text2 = _call_claude_vision(client, messages, model_to_use)
    logger.info(f"RAW LLM RESPONSE (2nd try): {result_text2}")
    parsed2 = _try_parse_json(result_text2, n_clusters)
    if parsed2 is not None:
        return parsed2
    # Fallback: parse_and_retry (через OpenAI)
    logger.error("Оба ответа невалидны, пытаемся извлечь JSON через parse_and_retry...")
    openai_api_key = get_secret("OPENAI_API_KEY")
    from .response_parser import parse_and_retry
    return parse_and_retry(result_text2, n_clusters, "Claude", openai_api_key)

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
