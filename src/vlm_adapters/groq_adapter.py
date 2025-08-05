import os
import json
import base64
import logging
import traceback
import datetime
from openai import OpenAI
from .cost_tracker import track_api_cost

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = "grok-2-vision-1212"

# --- Получение ключа ---
def get_secret(secret_name):
    secret = os.environ.get(secret_name)
    if secret:
        logger.info(f"Ключ {secret_name} успешно получен из переменных окружения")
        return secret
    try:
        secrets_file = 'secrets.json'
        # Проверяем путь к файлу
        if not os.path.exists(secrets_file):
            # Пробуем искать в директории проекта
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            secrets_file = os.path.join(root_dir, 'secrets.json')
            if not os.path.exists(secrets_file):
                logger.error(f"Файл secrets.json не найден ни в текущей директории, ни в корне проекта: {root_dir}")
                return None

        with open(secrets_file, 'r', encoding='utf-8') as f:
            secrets = json.load(f)
            secret = secrets.get(secret_name)
            if secret:
                logger.info(f"Ключ {secret_name} успешно получен из {secrets_file}")
                return secret
            else:
                logger.error(f"Ключ {secret_name} не найден в {secrets_file}")
                return None
    except Exception as e:
        logger.error(f"Не удалось прочитать секрет {secret_name}: {e}")
        return None

def get_groq_client():
    # Используем XAI_API_KEY для работы с X.AI API
    api_key = get_secret("XAI_API_KEY")
    if not api_key:
        error_msg = "XAI_API_KEY не найден в окружении или secrets.json"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("Инициализация клиента X.AI/Grok...")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",  # Используем правильный URL для X.AI
    )

def check_groq_api():
    """
    Проверяет валидность ключа X.AI API.
    Возвращает (True, None) если все в порядке, иначе (False, error_message).
    """
    logger.info("Проверка ключа X.AI API...")
    try:
        # Проверка валидности ключа через простой запрос
        client = get_groq_client()
        response = client.chat.completions.create(
            model="grok-1",  # Используем базовую модель для проверки
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        
        logger.info(f"X.AI API доступен и ключ валиден. Ответ: {response.choices[0].message.content}")
        return True, None
    except Exception as e:
        error_msg = f"Ошибка при проверке X.AI API: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return False, error_msg

def encode_image_to_base64(image_path):
    if not os.path.exists(image_path):
        logger.error(f"Файл изображения не найден: {image_path}")
        raise FileNotFoundError(f"Файл изображения не найден: {image_path}")
        
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

def _call_groq_vision(client, messages, model_to_use, temperature):
    response = client.chat.completions.create(
        model=model_to_use,
        messages=messages,
        temperature=temperature,
        max_tokens=4000,
    )
    
    # Отслеживаем стоимость
    try:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        track_api_cost(
            provider="groq",
            model=model_to_use,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=response.id,
            additional_info={
                "model": model_to_use,
                "temperature": temperature,
                "max_tokens": 4000
            }
        )
    except Exception as e:
        logger.warning(f"Не удалось отследить стоимость запроса Groq: {e}")
    
    return response.choices[0].message.content

def groq_vision_categorize(image_path, mask_path, n_clusters, legend_image_path=None, model_name=None, legend_description=None, temperature=0.2, seed=None, user_prompt_text=None, **kwargs):
    """
    Категоризация кластеров через Grok-2-Vision. Возвращает dict по кластерам.
    """
    try:
        # Проверка существования файлов изображений
        for path, name in [(image_path, "изображение"), (mask_path, "маска")]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Файл {name} не найден: {path}")
            logger.info(f"Файл {name} найден: {path} ({os.path.getsize(path)} байт)")

        client = get_groq_client()
        if user_prompt_text is not None:
            prompt = user_prompt_text
        else:
            prompt = get_prompt_text(n_clusters, legend_description)
        if legend_description:
            prompt += f"\n\n{legend_description}\n"
        
        # Формируем сообщения
        messages = [
            {"role": "system", "content": "You are a professional remote-sensing analyst working with satellite imagery."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
            ]}
        ]
        
        # Добавляем изображения
        # Оригинальное RGB изображение
        try:
            image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image_to_base64(image_path)}"}}
            messages[1]["content"].append(image_content)
        except Exception as e:
            logger.error(f"Ошибка при кодировании RGB изображения: {e}")
            raise
        
        # Маска кластеризации
        try:
            mask_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image_to_base64(mask_path)}"}}
            messages[1]["content"].append(mask_content)
        except Exception as e:
            logger.error(f"Ошибка при кодировании маски: {e}")
            raise
        
        # Добавляем легенду, если есть
        if legend_image_path and os.path.exists(legend_image_path):
            try:
                legend_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image_to_base64(legend_image_path)}"}}
                messages[1]["content"].append(legend_content)
            except Exception as e:
                logger.warning(f"Ошибка при кодировании легенды: {e}")
        
        # Используем указанную модель или модель по умолчанию
        model_to_use = model_name if model_name else MODEL_NAME
        
        logger.info(f"Отправляем запрос к X.AI/Grok: {model_to_use}, длина промпта: {len(prompt)}")
        
        # Первый запрос
        result_text = _call_groq_vision(client, messages, model_to_use, temperature)
        logger.info(f"RAW LLM RESPONSE (1st try): {result_text}")
        parsed = _try_parse_json(result_text, n_clusters)
        if parsed is not None:
            return parsed
        # Второй запрос
        logger.warning("Первый ответ невалиден, повторяем запрос к той же модели...")
        result_text2 = _call_groq_vision(client, messages, model_to_use, temperature)
        logger.info(f"RAW LLM RESPONSE (2nd try): {result_text2}")
        parsed2 = _try_parse_json(result_text2, n_clusters)
        if parsed2 is not None:
            return parsed2
        # Fallback: parse_and_retry (через OpenAI)
        logger.error("Оба ответа невалидны, пытаемся извлечь JSON через parse_and_retry...")
        openai_api_key = get_secret("OPENAI_API_KEY")
        from .response_parser import parse_and_retry
        return parse_and_retry(result_text2, n_clusters, "Grok", openai_api_key)
    except Exception as e:
        logger.error(f"Ошибка при работе с X.AI/Grok: {e}")
        raise

def _try_parse_json(result_text, n_clusters):
    decoder = json.JSONDecoder()
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
