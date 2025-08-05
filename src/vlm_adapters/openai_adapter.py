import os
import openai
import base64
import json
import re
import logging
import time
import numpy as np
import imageio.v2 as imageio
from openai import OpenAI
import datetime
from .response_parser import parse_and_retry
from .cost_tracker import track_api_cost

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_secret(secret_name):
    """
    Получает значение секрета из переменной окружения или из файла secrets.json
    """
    logger.info(f"Ищем секрет {secret_name} в переменных окружения")
    # Проверяем наличие секрета в переменных окружения
    secret_value = os.environ.get(secret_name)
    if secret_value:
        logger.info(f"Получен секрет {secret_name} из переменной окружения")
        return secret_value
    
    # Если нет в переменных окружения, ищем в файле secrets.json
    secrets_file = "secrets.json"
    # Если не нашли в текущей директории, ищем в корне проекта
    if not os.path.exists(secrets_file):
        secrets_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "secrets.json")
    
    logger.info(f"Ищем секрет {secret_name} в файле {secrets_file}")
    if os.path.exists(secrets_file):
        try:
            with open(secrets_file, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
                if secret_name in secrets:
                    logger.info(f"Получен секрет {secret_name} из файла {secrets_file}")
                    return secrets[secret_name]
        except Exception as e:
            logger.error(f"Ошибка при чтении файла секретов: {e}")
    
    logger.warning(f"Секрет {secret_name} не найден")
    return None

def get_openai_client():
    """
    Инициализирует и возвращает клиент OpenAI API
    """
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API ключ OpenAI не найден. Укажите его в переменной окружения OPENAI_API_KEY или в файле secrets.json")
    
    # Создаем клиент OpenAI
    client = OpenAI(api_key=api_key)
    logger.info("Клиент OpenAI успешно инициализирован")
    return client

def encode_image_to_base64(image_path):
    """Кодирование изображения в base64 для отправки в API."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def convert_mask_to_grayscale(mask_path):
    """Преобразует цветную маску в оттенки серого, где каждый кластер имеет свой уровень серого."""
    mask_arr = imageio.imread(mask_path)
    # Если маска RGB (3D), преобразуем в 2D (берём только первый канал)
    if mask_arr.ndim == 3:
        # Если маска цветная, предполагаем, что все каналы одинаковы (или используем только один)
        mask_arr = mask_arr[..., 0]

    uniq = np.unique(mask_arr)
    gray_mask = np.zeros_like(mask_arr, dtype=np.uint8)
    for i, val in enumerate(uniq):
        gray_level = int(255 * i / max(1, len(uniq) - 1))
        gray_mask[mask_arr == val] = gray_level

    # Сохраняем временный файл
    out_path = mask_path.replace('.png', '_gray_tmp.png')
    imageio.imwrite(out_path, gray_mask)
    return out_path

def get_color_name(rgb):
    """Return a descriptive name for an RGB color."""
    r, g, b = rgb
    
    # Simple color naming based on dominant channels
    if r > 200 and g > 200 and b > 200:
        return "white/very light"
    elif r < 50 and g < 50 and b < 50:
        return "black/very dark"
    
    # Colors with one dominant channel
    elif r > 150 and g < 100 and b < 100:
        return "red/reddish"
    elif r < 100 and g > 150 and b < 100:
        return "green/greenish" 
    elif r < 100 and g < 100 and b > 150:
        return "blue/bluish"
        
    # Colors with two dominant channels
    elif r > 150 and g > 150 and b < 100:
        return "yellow/yellowish"
    elif r > 150 and g < 100 and b > 150:
        return "magenta/pinkish"
    elif r < 100 and g > 150 and b > 150:
        return "cyan/bluish-green"
    
    # Browns and grays
    elif abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
        if r < 128:
            return "dark gray"
        else:
            return "light gray"
    elif r > 100 and g > 50 and g < 150 and b < 100:
        return "brown/brownish"
    
    # Default for other colors
    else:
        return "mixed color"

def _call_openai_vision(client, messages, model_name, temperature, seed, **kwargs):
    model_lower = model_name.lower() if model_name else ""
    completion_kwargs = dict(
        model=model_name,
        messages=messages,
        seed=seed,
        **kwargs
    )
    if any(x in model_lower for x in ["o4-mini", "o3", "o1"]):
        completion_kwargs["max_completion_tokens"] = 4096
    else:
        completion_kwargs["max_tokens"] = 4096
        completion_kwargs["temperature"] = temperature
    
    response = client.chat.completions.create(
        **completion_kwargs
    )
    
    # Отслеживаем стоимость
    try:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        track_api_cost(
            provider="openai",
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=response.id,
            additional_info={
                "model": model_name,
                "temperature": temperature,
                "max_tokens": completion_kwargs.get("max_tokens", completion_kwargs.get("max_completion_tokens"))
            }
        )
    except Exception as e:
        logger.warning(f"Не удалось отследить стоимость запроса: {e}")
    
    return response.choices[0].message.content

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

def openai_vision_categorize(image_path, mask_path, n_clusters, legend_image_path=None, model_name=None, legend_description=None, temperature=0.2, seed=None, user_prompt_text=None, **kwargs):
    """
    Категоризирует сегменты маски сегментации с помощью OpenAI Vision API.
    
    Parameters:
    -----------
    image_path : str
        Путь к изображению RGB (исходное изображение)
    mask_path : str
        Путь к маске сегментации (PNG)
    n_clusters : int
        Количество кластеров в маске
    legend_image_path : str, optional
        Путь к PNG изображению с легендой кластеров (если есть)
    model_name : str, optional
        Название модели OpenAI (например, 'gpt-4o-2024-08-06')
        Если не указано — используется 'gpt-4.1-2025-04-14'
    temperature : float, optional
        Температура для генерации ответа
    seed : int, optional
        Сид для генерации ответа
    user_prompt_text : str, optional
        Текст пользовательского prompt
    Returns:
    --------
    dict
        Словарь с категориями для каждого кластера
    """
    # Проверяем наличие ключа API
    api_key = None
    logger.info("Ищем секрет OPENAI_API_KEY в переменных окружения")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("Ищем секрет OPENAI_API_KEY в файле secrets.json")
        try:
            secrets_path = os.path.join(os.path.dirname(__file__), "../../secrets.json")
            with open(secrets_path, "r") as f:
                secrets = json.load(f)
                api_key = secrets.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("Получен секрет OPENAI_API_KEY из файла secrets.json")
        except Exception as e:
            logger.error(f"Ошибка при чтении secrets.json: {e}")
    if not api_key:
        raise ValueError("OPENAI_API_KEY не найден ни в переменных окружения, ни в файле secrets.json")
    client = OpenAI(api_key=api_key)
    logger.info("Клиент OpenAI успешно инициализирован")

    if user_prompt_text is not None:
        prompt = user_prompt_text
    else:
        prompt = get_prompt_text(n_clusters)

    system_message = """You are an expert remote sensing analyst specializing in land cover classification from satellite imagery. \nYour task is to analyze segmentation masks and identify land cover types based on the WorldCover classification system.\nIMPORTANT: The colors in the segmentation mask are arbitrary - they do NOT indicate the actual land cover type. Your classification must be based on analyzing the content in the original satellite image.\nProvide thorough, precise, and scientifically accurate analysis of each segment.\nConsider spatial patterns, textures, shapes, and contextual relationships when making your determinations.\nMaintain scientific objectivity and indicate confidence levels appropriately."""

    # --- ГАРАНТИРУЕМ grayscale PNG для маски ---
    gray_mask_path = convert_mask_to_grayscale(mask_path)
    image_b64 = encode_image_to_base64(image_path)
    mask_b64 = encode_image_to_base64(gray_mask_path)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{mask_b64}"}}
        ]}
    ]
    if legend_image_path and os.path.exists(legend_image_path):
        legend_b64 = encode_image_to_base64(legend_image_path)
        messages[1]["content"].append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{legend_b64}"}}
        )
    model_lower = model_name.lower() if model_name else ""
    completion_kwargs = dict(
        model=model_name,
        messages=messages,
        seed=seed,
        **kwargs
    )
    if any(x in model_lower for x in ["o4-mini", "o3", "o1"]):
        completion_kwargs["max_completion_tokens"] = 4096
    else:
        completion_kwargs["max_tokens"] = 4096
        completion_kwargs["temperature"] = temperature
    response = client.chat.completions.create(
        **completion_kwargs
    )
    # Удаляем временный файл с маской в оттенках серого
    try:
        os.remove(gray_mask_path)
    except Exception:
        pass
    result_text = response.choices[0].message.content
    logger.info(f"RAW LLM RESPONSE (1st try): {result_text}")
    api_key = api_key  # уже получен выше
    parsed = parse_and_retry(result_text, n_clusters, "OpenAI", api_key)
    if parsed is not None:
        return parsed
    logger.warning("Первый ответ невалиден, повторяем запрос к той же модели...")
    result_text2 = _call_openai_vision(client, messages, model_name, temperature, seed, **kwargs)
    logger.info(f"RAW LLM RESPONSE (2nd try): {result_text2}")
    parsed2 = parse_and_retry(result_text2, n_clusters, "OpenAI", api_key)
    if parsed2 is not None:
        return parsed2
    raise ValueError("Оба ответа OpenAI невалидны, не удалось извлечь JSON")

def openai_vision_categorize_custom_prompt(image_path, mask_path, n_clusters, user_prompt_text, legend_image_path=None, model_name=None, legend_description=None, temperature=0.2, seed=None, **kwargs):
    """
    То же, что openai_vision_categorize, но prompt полностью задаётся пользователем (user_prompt_text).
    В user_prompt_text можно использовать {legend_description} и {n_clusters} для подстановки.
    """
    # Проверяем наличие ключа API
    api_key = None
    logger.info("Ищем секрет OPENAI_API_KEY в переменных окружения")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("Ищем секрет OPENAI_API_KEY в файле secrets.json")
        try:
            secrets_path = os.path.join(os.path.dirname(__file__), "../../secrets.json")
            with open(secrets_path, "r") as f:
                secrets = json.load(f)
                api_key = secrets.get("OPENAI_API_KEY")
                if api_key:
                    logger.info("Получен секрет OPENAI_API_KEY из файла secrets.json")
        except Exception as e:
            logger.error(f"Ошибка при чтении secrets.json: {e}")
    if not api_key:
        raise ValueError("OPENAI_API_KEY не найден ни в переменных окружения, ни в файле secrets.json")
    client = OpenAI(api_key=api_key)
    logger.info("Клиент OpenAI успешно инициализирован (custom prompt)")

    # Формируем prompt
    prompt_text = user_prompt_text.format(legend_description=legend_description or "", n_clusters=n_clusters)

    # System message (тот же, что и в оригинале)
    system_message = """You are an expert remote sensing analyst specializing in land cover classification from satellite imagery. \nYour task is to analyze segmentation masks and identify land cover types based on the WorldCover classification system.\nIMPORTANT: The colors in the segmentation mask are arbitrary - they do NOT indicate the actual land cover type. Your classification must be based on analyzing the content in the original satellite image.\nProvide thorough, precise, and scientifically accurate analysis of each segment.\nConsider spatial patterns, textures, shapes, and contextual relationships when making your determinations.\nMaintain scientific objectivity and indicate confidence levels appropriately."""

    image_b64 = encode_image_to_base64(image_path)
    mask_b64 = encode_image_to_base64(mask_path)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": [
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{mask_b64}"}}
        ]}
    ]
    if legend_image_path and os.path.exists(legend_image_path):
        legend_b64 = encode_image_to_base64(legend_image_path)
        messages[1]["content"].append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{legend_b64}"}}
        )
    model_lower = model_name.lower() if model_name else ""
    completion_kwargs = dict(
        model=model_name,
        messages=messages,
        seed=seed,
        **kwargs
    )
    if any(x in model_lower for x in ["o4-mini", "o3", "o1"]):
        completion_kwargs["max_completion_tokens"] = 4096
    else:
        completion_kwargs["max_tokens"] = 4096
        completion_kwargs["temperature"] = temperature
    response = client.chat.completions.create(
        **completion_kwargs
    )
    result_text = response.choices[0].message.content
    # Логируем полный ответ LLM
    logger.info(f"RAW LLM RESPONSE: {result_text}")
    # Парсим первый JSON-объект в ответе
    decoder = json.JSONDecoder()
    start_idx = result_text.find('{')
    if start_idx >= 0:
        json_text = result_text[start_idx:]
        logger.info(f"Извлечен JSON-подстрока длиной {len(json_text)} символов для парсинга")
    else:
        json_text = result_text
        logger.info("JSON не найден в ответе, пробуем парсить весь ответ")
    try:
        result, idx = decoder.raw_decode(json_text)
        # Проверяем ключи ответа (должны быть цифрами)
        bad_keys = [k for k in result.keys() if not str(k).isdigit()]
        if bad_keys:
            raise json.JSONDecodeError(f"Invalid keys {bad_keys}", json_text, 0)
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Не удалось разобрать JSON из ответа OpenAI: {e}")
        logger.error(f"Начало ответа: {result_text[:300]}")
        # Сохраняем полный сырой ответ для отладки
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        raw_file = f"openai_raw_response_{timestamp}.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(result_text)
        logger.info(f"Сохранён несфоматированный ответ в файл {raw_file}")
        # Вторичная попытка: просим GPT-4.1-nano извлечь корректный JSON
        retry_prompt = f"""
Your previous response could not be parsed as valid JSON. Here is the full raw response:
{result_text}

Please extract and return a valid JSON object mapping each cluster number (0-{n_clusters}) to an object with keys 'category', 'confidence', and 'reasoning'. Use only JSON with no additional text. Available categories: Tree cover, Shrubland, Grassland, Cropland, Built-up, Bare / sparse vegetation, Snow and ice, Permanent water bodies, Herbaceous wetland, Mangroves, Moss and lichen.
"""
        retry_response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a JSON extraction assistant."},
                {"role": "user", "content": retry_prompt}
            ],
            temperature=temperature,
            max_tokens=4000
        )
        result_text2 = retry_response.choices[0].message.content
        # Парсим первый JSON-объект во втором ответе
        start_idx2 = result_text2.find('{')
        json_text2 = result_text2[start_idx2:] if start_idx2 >= 0 else result_text2
        try:
            result2, idx2 = decoder.raw_decode(json_text2)
            logger.info(f"Успешно получены категории из второй попытки для {len(result2)} кластеров")
            return result2
        except json.JSONDecodeError as e2:
            logger.error(f"Не удалось разобрать JSON из второго ответа OpenAI: {e2}")
            logger.error(f"Начало второго ответа: {result_text2[:300]}")
            raise ValueError(f"OpenAI second response is not valid JSON: {e2}")

def get_prompt_text(n_clusters, legend_description=None):
    """
    Новый подробный prompt для кластеризации WorldCover (см. claude_adapter.py)
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
