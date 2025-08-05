import json
import datetime
import logging
from json import JSONDecoder, JSONDecodeError
from openai import OpenAI

logger = logging.getLogger(__name__)

def extract_all_json_objects(text):
    """
    Извлекает все JSON-объекты из текста, возвращает список (length, obj).
    """
    decoder = JSONDecoder()
    candidates = []
    for pos, ch in enumerate(text):
        if ch == '{':
            try:
                obj, length = decoder.raw_decode(text[pos:])
                candidates.append((length, obj))
            except JSONDecodeError:
                continue
    return candidates

def merge_json_candidates(candidates):
    """
    Если все объекты — dict с числовыми ключами, склеивает их в один dict.
    Если есть один большой — возвращает его.
    """
    if not candidates:
        return None
    # Сортируем по размеру (длина)
    candidates = sorted(candidates, key=lambda x: -x[0])
    # Если только один — возвращаем его
    if len(candidates) == 1:
        return candidates[0][1]
    # Если есть один большой (по числу кластеров)
    max_obj = max(candidates, key=lambda x: len(x[1]) if isinstance(x[1], dict) else 0)[1]
    if isinstance(max_obj, dict) and all(str(k).isdigit() for k in max_obj.keys()):
        return max_obj
    # Если все объекты — dict с одним числовым ключом, склеиваем
    merged = {}
    for _, obj in candidates:
        if isinstance(obj, dict) and len(obj) == 1 and all(str(k).isdigit() for k in obj.keys()):
            merged.update(obj)
    if merged:
        return merged
    # Если все объекты — dict с числовыми ключами, но разными, склеиваем
    all_dicts = [obj for _, obj in candidates if isinstance(obj, dict) and all(str(k).isdigit() for k in obj.keys())]
    if all_dicts:
        for d in all_dicts:
            for k, v in d.items():
                if k not in merged:
                    merged[k] = v
        if merged:
            return merged
    return None

def parse_and_retry(text: str, n_clusters: int, adapter_label: str, openai_api_key: str, temperature: float = 0.2) -> dict:
    """
    Извлекает все JSON-объекты, объединяет, если возможно. Если не удалось — fallback на OpenAI.
    """
    logger.info(f"RAW LLM RESPONSE ({adapter_label}): {text}")
    candidates = extract_all_json_objects(text)
    merged = merge_json_candidates(candidates)
    if merged and all(str(k).isdigit() for k in merged.keys()):
        return merged
    # Ошибка парсинга или неверные ключи
    logger.error(f"JSON parse failed ({adapter_label}): no valid merged JSON")
    logger.error(f"Response start: {text[:300]}")
    # Сохраняем сырой ответ
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    raw_file = f"{adapter_label.lower()}_raw_response_{timestamp}.txt"
    with open(raw_file, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"Saved raw response to {raw_file}")
    # Повторный запрос к OpenAI GPT-4.1-nano
    openai_client = OpenAI(api_key=openai_api_key)
    retry_prompt = f"""
Your previous response from {adapter_label} could not be parsed as valid JSON. Here is the full raw response:
{text}

Please extract and return a valid JSON object mapping each cluster number (0-{n_clusters}) to an object with keys 'category', 'confidence', and 'reasoning'. Use only JSON with no additional text. Available categories: Tree cover, Shrubland, Grassland, Cropland, Built-up, Bare / sparse vegetation, Snow and ice, Permanent water bodies, Herbaceous wetland, Mangroves, Moss and lichen.
"""
    retry_response = openai_client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": "You are a JSON extraction assistant."},
            {"role": "user", "content": retry_prompt}
        ],
        temperature=temperature,
        max_tokens=4000
    )
    text2 = retry_response.choices[0].message.content
    logger.info(f"RAW LLM RESPONSE RETRY ({adapter_label} -> OpenAI): {text2}")
    candidates2 = extract_all_json_objects(text2)
    merged2 = merge_json_candidates(candidates2)
    if not merged2:
        raise ValueError(f"No JSON object found in retry response ({adapter_label})")
    bad_keys2 = [k for k in merged2.keys() if not str(k).isdigit()]
    if bad_keys2:
        raise ValueError(f"Invalid keys after retry ({adapter_label}): {bad_keys2}")
    return merged2 