import numpy as np
import os
import sys
import json
import random
from datetime import datetime
import sys
import os

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    # Ищем .env файл в корне проекта
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"Загружен .env файл: {env_path}")
    else:
        print(f".env файл не найден: {env_path}")
except ImportError:
    print("python-dotenv не установлен, переменные окружения могут не загрузиться")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.utils.tiling import load_channels_from_files, prepare_multichannel_tile
from src.clustering_methods.clustering_methods import cluster_tiles
from skimage.io import imsave
import rasterio
from src.utils.worldcover import load_worldcover_mask_by_coords, get_worldcover_legend, compare_masks, crop_and_resize_worldcover
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import to_rgb
from src.vlm_adapters.openai_adapter import openai_vision_categorize, get_prompt_text as openai_prompt
from src.vlm_adapters.claude_adapter import claude_vision_categorize, get_prompt_text as claude_prompt
from src.vlm_adapters.groq_adapter import groq_vision_categorize, get_prompt_text as groq_prompt
from src.vlm_adapters.qwen_adapter import qwen_vision_categorize, get_prompt_text as qwen_prompt
from src.vlm_adapters.friendli_adapter import friendli_vision_categorize, get_prompt_text as friendli_prompt
from src.vlm_adapters.ibm_granite_adapter import ibm_granite_vision_categorize, get_prompt_text as ibm_prompt
from src.vlm_adapters.gemini_adapter import gemini_vision_categorize, get_prompt_text as gemini_prompt
from src.vlm_adapters.qwen2_5_vl_72b_instruct_awq_friendli_adapter import qwen2_5_vl_72b_instruct_awq_friendli_vision_categorize, get_prompt_text as qwen2_5_prompt
from src.vlm_adapters.qwen_qvq_72b_preview_friendli_adapter import qwen_qvq_72b_preview_friendli_vision_categorize, get_prompt_text as qwen_qvq_prompt
from src.vlm_adapters.cost_tracker import print_cost_summary, get_cost_summary
from PIL import Image
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
try:
    import magic
    HAVE_MAGIC = True
except ImportError:
    HAVE_MAGIC = False

CATEGORY_COLORS = {
    "tree_cover": [0, 100, 0],
    "shrubland": [255, 187, 34],
    "grassland": [255, 255, 76],
    "cropland": [240, 150, 255],
    "built-up": [250, 0, 0],
    "bare_sparse_vegetation": [180, 180, 180],
    "snow_and_ice": [240, 240, 240],
    "permanent_water_bodies": [0, 100, 200],
    "herbaceous_wetland": [0, 150, 160],
    "mangroves": [0, 207, 117],
    "moss_and_lichen": [250, 230, 160],
    "unknown": [0, 0, 0],
    "open_water": [0, 100, 200],
    "water": [0, 100, 200],
}

# Parameters
N_TILES = 2  # Уменьшено для тестирования
TILES_FILE = "results/tiles.json"
RESULTS_ROOT = "results"

# Ensure log directory exists
os.makedirs(RESULTS_ROOT, exist_ok=True)

# MODELS - edit as needed
MODELS = [
    {"name": "o4-mini", "api": "openai"},
    {"name": "claude-3-5-haiku-20241022", "api": "claude"},
]

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(RESULTS_ROOT, "test_clustering_final_tiles.log"), mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LoggerWriter:
    def __init__(self, level):
        self.level = level
        self.buffer = ''
    def write(self, message):
        if message and message != '\n':
            self.buffer += message
        if '\n' in message:
            self.level(self.buffer)
            self.buffer = ''
    def flush(self):
        pass

sys.stdout = LoggerWriter(logger.info)
sys.stderr = LoggerWriter(logger.error)

def get_or_create_tiles(n_tiles=N_TILES, tile_size=512, border=200):
    if os.path.exists(TILES_FILE):
        with open(TILES_FILE, 'r', encoding='utf-8') as f:
            tiles = json.load(f)
        logger.info(f"Loaded {len(tiles)} tiles from {TILES_FILE}")
        return tiles
    # Generate new tiles
    folder = 'cropped_images'
    base_name = 'cropped_T36TWS_20230605T083601'
    channel = "B02"
    with rasterio.open(os.path.join(folder, f"{base_name}_{channel}_20m.tif")) as src:
        H, W = src.height, src.width
    tiles = []
    for _ in range(n_tiles):
        x0 = random.randint(border, W - border - tile_size)
        y0 = random.randint(border, H - border - tile_size)
        tiles.append({'x0': x0, 'y0': y0})
    os.makedirs(os.path.dirname(TILES_FILE), exist_ok=True)
    with open(TILES_FILE, 'w', encoding='utf-8') as f:
        json.dump(tiles, f, indent=2)
    logger.info(f"Saved {n_tiles} tiles to {TILES_FILE}")
    return tiles

# === ДОБАВЛЯЕМ ФУНКЦИЮ ДЛЯ НЕПЕРЕСЕКАЮЩИХСЯ ТАЙЛОВ ===
def generate_non_overlapping_tiles(folder, base_name, channel, tile_size, border, n_tiles, seed=12, coords_file=None):
    import json
    random.seed(seed)
    np.random.seed(seed)
    if coords_file and os.path.exists(coords_file):
        with open(coords_file, 'r', encoding='utf-8') as f:
            coords = json.load(f)
        return [(int(x), int(y)) for x, y in coords]
    with rasterio.open(os.path.join(folder, f"{base_name}_{channel}_20m.tif")) as src:
        H, W = src.height, src.width
    tiles = []
    attempts = 0
    max_attempts = 10000
    while len(tiles) < n_tiles and attempts < max_attempts:
        x0 = random.randint(border, W - border - tile_size)
        y0 = random.randint(border, H - border - tile_size)
        new_box = (x0, y0, x0 + tile_size, y0 + tile_size)
        overlap = False
        for (tx0, ty0, tx1, ty1) in tiles:
            if not (new_box[2] <= tx0 or new_box[0] >= tx1 or new_box[3] <= ty0 or new_box[1] >= ty1):
                overlap = True
                break
        if not overlap:
            tiles.append(new_box)
        attempts += 1
    if len(tiles) < n_tiles:
        raise RuntimeError("Не удалось сгенерировать непересекающиеся тайлы")
    coords = [(x0, y0) for (x0, y0, _, _) in tiles]
    if coords_file:
        os.makedirs(os.path.dirname(coords_file), exist_ok=True)
        with open(coords_file, 'w', encoding='utf-8') as f:
            json.dump(coords, f)
    return coords

def ensure_valid_png(path):
    import os
    from PIL import Image
    try:
        img = Image.open(path).convert('RGB')
        img.save(path, format='PNG')
        img.close()
        with open(path, 'rb') as f:
            os.fsync(f.fileno())
        # Проверка существования и открытия
        if not os.path.exists(path):
            print(f'[ERROR] PNG-файл не существует: {os.path.abspath(path)}')
            return False
        try:
            img2 = Image.open(path)
            if img2.mode != 'RGB' or img2.getbands() != ('R','G','B'):
                print(f'[ERROR] PNG не RGB 8bit: {os.path.abspath(path)} mode={img2.mode} bands={img2.getbands()}')
                return False
            img2.close()
        except Exception as e:
            print(f'[ERROR] Не удалось открыть PNG {os.path.abspath(path)}: {e}')
            return False
        return True
    except Exception as e:
        print(f'[WARN] Не удалось пересохранить PNG {path}: {e}')
        return False

def save_tile_tci_png(folder, base_name, x0, y0, tile_size, out_path, tile_dict):
    tci_path = os.path.join(folder, f"{base_name}_TCI_20m.tif")
    if os.path.exists(tci_path):
        with rasterio.open(tci_path) as src:
            tci = src.read(window=rasterio.windows.Window(x0, y0, tile_size, tile_size))
            tci = np.transpose(tci, (1, 2, 0))
            p_low, p_high = np.percentile(tci, (2, 98))
            tci_enhanced = np.clip((tci - p_low) / (p_high - p_low + 1e-6), 0, 1)
            arr = (tci_enhanced * 255).astype(np.uint8)
            print(f'[DEBUG] save_tile_tci_png: dtype={arr.dtype}, min={arr.min()}, max={arr.max()}')
            arr = arr.astype(np.uint8)
            img = Image.fromarray(arr, mode='RGB')
            img.save(out_path)
    else:
        r = tile_dict["B04"]
        g = tile_dict["B03"]
        b = tile_dict["B02"]
        rgb = np.stack([r, g, b], axis=-1).astype(np.float32)
        p_low, p_high = np.percentile(rgb, (2, 98))
        rgb = np.clip((rgb - p_low) / (p_high - p_low + 1e-6), 0, 1)
        arr = (rgb * 255).astype(np.uint8)
        print(f'[DEBUG] save_tile_tci_png: dtype={arr.dtype}, min={arr.min()}, max={arr.max()}')
        arr = arr.astype(np.uint8)
        img = Image.fromarray(arr, mode='RGB')
        img.save(out_path)

def save_colored_mask_and_legend(mask, out_prefix):
    uniq = np.unique(mask)
    n = len(uniq)
    cmap = cm.get_cmap('tab20', n)
    colors = [tuple(int(255*x) for x in to_rgb(cmap(i))) for i in range(n)]
    color_map = {int(cluster): list(colors[i]) for i, cluster in enumerate(uniq)}
    legend_path = f"{out_prefix}_colors.json"
    os.makedirs(os.path.dirname(legend_path), exist_ok=True)
    with open(legend_path, 'w', encoding='utf-8') as f:
        json.dump(color_map, f, indent=2)
    h, w = mask.shape
    rgb_mask = np.zeros((h, w, 3), dtype=np.uint8)
    for i, cluster in enumerate(uniq):
        rgb_mask[mask == cluster] = colors[i]
    print(f'[DEBUG] save_colored_mask_and_legend: dtype={rgb_mask.dtype}, min={rgb_mask.min()}, max={rgb_mask.max()}')
    rgb_mask = rgb_mask.astype(np.uint8)
    png_path = f"{out_prefix}.png"
    img = Image.fromarray(rgb_mask, mode='RGB')
    img.save(png_path)
    return png_path, legend_path, color_map

# === МЕТОД 1: СОЗДАНИЕ МАСКИ В ОТТЕНКАХ СЕРОГО ===
def save_gray_mask_and_legend(mask, out_prefix):
    """Создает маску в оттенках серого и легенду для Method 1"""
    uniq = np.unique(mask)
    n = len(uniq)
    
    # Создаем оттенки серого: 0, 51, 102, 153, 204, 255
    gray_values = [0, 51, 102, 153, 204, 255]
    gray_map = {int(cluster): gray_values[i] for i, cluster in enumerate(uniq)}
    
    # Сохраняем легенду
    legend_path = f"{out_prefix}_gray_legend.json"
    os.makedirs(os.path.dirname(legend_path), exist_ok=True)
    with open(legend_path, 'w', encoding='utf-8') as f:
        json.dump(gray_map, f, indent=2)
    
    # Создаем маску в оттенках серого
    h, w = mask.shape
    gray_mask = np.zeros((h, w), dtype=np.uint8)
    for cluster in uniq:
        gray_mask[mask == cluster] = gray_map[int(cluster)]
    
    # Сохраняем маску
    png_path = f"{out_prefix}_gray.png"
    img = Image.fromarray(gray_mask, mode='L')
    img.save(png_path)
    
    return png_path, legend_path, gray_map

def process_method_model_for_tile_method1(tile_idx, x0, y0, tile_dir, tile_all, tile_ndvi, tci_path, wc_mask_cropped, method, model, wc_legend, code_to_category, category2code):
    """Обработка для Method 1: создание масок в оттенках серого"""
    import numpy as np
    from PIL import Image
    import json
    logger = globals().get('logger', None)
    try:
        # Кластеризация
        if method == "watershed_ndvi":
            result = cluster_tiles([tile_ndvi], method=method)
            mask = result["mask"] if isinstance(result, dict) and 'mask' in result else result
        elif method == "unet":
            result = cluster_tiles([tile_all], method="unet_encoder_kmeans", n_clusters=6)
            mask = result["mask"]
        else:
            result = cluster_tiles([tile_all], method=method)
            mask = result["mask"] if isinstance(result, dict) and 'mask' in result else result
        
        # Сохраняем цветную маску (как обычно)
        method_prefix = os.path.join(tile_dir, f"{method}_mask_{tile_idx}")
        method_path, method_legend_path, color_legend = save_colored_mask_and_legend(mask, method_prefix)
        
        # === МЕТОД 1: СОЗДАЕМ МАСКУ В ОТТЕНКАХ СЕРОГО ===
        gray_mask_path, gray_legend_path, gray_map = save_gray_mask_and_legend(mask, method_prefix)
        
        model_name = model['name']
        logger and logger.info(f"Категоризируем кластеры методом {method} с помощью {model_name} (Method 1: серая маска + легенда)...")
        
        # === МЕТОД 1: ПЕРЕДАЕМ В VLM СЕРАЮ МАСКУ + ЛЕГЕНДУ + ОРИГИНАЛЬНОЕ ИЗОБРАЖЕНИЕ ===
        n_clusters = len(np.unique(mask))
        legend_description = f"Gray value mapping: {gray_map}"
        
        if model['api'] == 'openai':
            prompt = openai_prompt(n_clusters, legend_description)
            vlm_func = openai_vision_categorize
        elif model['api'] == 'claude':
            prompt = claude_prompt(n_clusters, legend_description)
            vlm_func = claude_vision_categorize
        elif model['api'] == 'groq':
            prompt = groq_prompt(n_clusters, legend_description)
            vlm_func = groq_vision_categorize
        elif model['api'] == 'qwen':
            prompt = qwen_prompt(n_clusters, legend_description)
            vlm_func = qwen_vision_categorize
        elif model['api'] == 'friendli':
            prompt = friendli_prompt(n_clusters, legend_description)
            vlm_func = friendli_vision_categorize
        elif model['api'] == 'ibm_granite':
            prompt = ibm_prompt(n_clusters, legend_description)
            vlm_func = ibm_granite_vision_categorize
        elif model['api'] == 'gemini':
            prompt = gemini_prompt(n_clusters, legend_description)
            vlm_func = gemini_vision_categorize
        elif model['api'] == 'qwen2_5_vl_72b_instruct_awq_friendli':
            prompt = qwen2_5_prompt(n_clusters, legend_description)
            vlm_func = qwen2_5_vl_72b_instruct_awq_friendli_vision_categorize
        elif model['api'] == 'qwen_qvq_72b_preview_friendli':
            prompt = qwen_qvq_prompt(n_clusters, legend_description)
            vlm_func = qwen_qvq_72b_preview_friendli_vision_categorize
        else:
            raise ValueError(f"Unknown model API: {model['api']}")
        
        try:
            # === МЕТОД 1: ПЕРЕДАЕМ СЕРАЮ МАСКУ + ЛЕГЕНДУ ===
            vlm_response = vlm_func(
                image_path=tci_path,
                mask_path=gray_mask_path,  # Серая маска
                n_clusters=len(np.unique(mask)),
                legend_image_path=gray_legend_path,  # Легенда для серой маски
                model_name=model_name,
                user_prompt_text=prompt,
                **model.get("extra_args", {})
            )
            
            # Сохраняем raw ответ
            raw_path = os.path.join(tile_dir, f"raw_vlm_response_{method}_{model_name}.txt")
            with open(raw_path, "w") as f:
                f.write(str(vlm_response))
                
        except Exception as e:
            logger and logger.error(f"[ERROR] Ошибка при получении VLM ответа: {e}")
            vlm_response = None
        
        # Обрабатываем ответ VLM
        vlm_categories = {}
        if vlm_response:
            try:
                if isinstance(vlm_response, str):
                    try:
                        result = json.loads(vlm_response)
                    except Exception as e:
                        logger and logger.error(f"[ERROR] Не удалось распарсить результат как JSON: {vlm_response}")
                        vlm_categories = {'error': 'failed_to_parse'}
                        result = None
                else:
                    result = vlm_response
                
                if result:
                    # Обрабатываем результат в зависимости от формата
                    if isinstance(result, dict):
                        vlm_categories = result
                    else:
                        vlm_categories = {'raw_response': str(result)}
                        
            except Exception as e:
                logger and logger.error(f"[ERROR] Ошибка при обработке ответа VLM: {e}")
                vlm_categories = {'error': str(e)}
        
        # Сохраняем результаты категоризации
        with open(os.path.join(tile_dir, f"{method}_mask_{model_name}_vlm_categories.json"), 'w', encoding='utf-8') as f:
            json.dump(vlm_categories, f, indent=2, ensure_ascii=False)
        
        logger and logger.info(f"Сохранены результаты категоризации для {method} + {model_name} (Method 1)")
        
    except Exception as e:
        logger and logger.error(f"[ERROR] Ошибка в process_method_model_for_tile_method1: {e}")

def main():
    logger.info(f'CWD: {os.getcwd()}')
    tile_size = 512
    border = 0
    folder = 'cropped_images'
    base_name = 'cropped_T36TWS_20230605T083601'
    channel = "B02"
    n_tiles = N_TILES
    global RESULTS_ROOT
    RESULTS_ROOT = f"tests/final_test/method_1/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    os.makedirs(RESULTS_ROOT, exist_ok=True)
    coords_file = os.path.join(RESULTS_ROOT, "tiles_coords.json")
    tiles = generate_non_overlapping_tiles(folder, base_name, channel, tile_size, border, n_tiles, seed=42, coords_file=coords_file)
    channels_all = ["B02", "B03", "B04", "B05", "B06", "B07", "B8A", "B11", "B12"]
    channels_ndvi = ["B04", "B8A"]
    methods = ["kmeans"]  # Уменьшено для тестирования
    wc_legend = get_worldcover_legend()
    code_to_category = {code: name.lower().replace(' / ', '_/_').replace(' ', '_') for code, (name, _) in wc_legend.items()}
    category2code = {name.lower().replace(' / ', '_/_').replace(' ', '_'): code for code, (name, _) in wc_legend.items()}
    import multiprocessing
    num_workers = max(1, os.cpu_count() - 1)
    for tile_idx, (x0, y0) in enumerate(tiles):
        logger.info(f"\n=== Tile {tile_idx+1}/{len(tiles)} (x0={x0}, y0={y0}) ===")
        tile_dir = os.path.join(RESULTS_ROOT, f"tile_{tile_idx}")
        os.makedirs(tile_dir, exist_ok=True)
        tile_dict_all = load_channels_from_files(folder, base_name, channels_all, tile_size=tile_size, x0=x0, y0=y0)
        tile_all = prepare_multichannel_tile(tile_dict_all)
        tile_dict_ndvi = load_channels_from_files(folder, base_name, channels_ndvi, tile_size=tile_size, x0=x0, y0=y0)
        tile_ndvi = np.stack([tile_dict_ndvi["B04"], tile_dict_ndvi["B8A"]], axis=-1)
        tci_path = os.path.join(tile_dir, f"tile_TCI_{tile_idx}.png")
        save_tile_tci_png(folder, base_name, x0, y0, tile_size, tci_path, tile_dict_all)
        ok = ensure_valid_png(tci_path)
        if not ok:
            logger.error(f'Invalid PNG for LLM: {os.path.abspath(tci_path)}, skip!')
            continue
        
        # Загружаем WorldCover с неинтерактивной аутентификацией
        logger.info("Загружаем WorldCover данные...")
        src_file = os.path.join(folder, f"{base_name}_B02_20m.tif")
        with rasterio.open(src_file) as src:
            src_crs = src.crs
            x_off, y_off = src.transform * (x0, y0)
            x_max, y_max = src.transform * (x0 + tile_size, y0 + tile_size)
            bbox_wgs84 = (x_off, y_max, x_max, y_off)
            
            # Получаем учетные данные из переменных окружения
            username = os.environ.get('TERRASCOPE_USERNAME')
            password = os.environ.get('TERRASCOPE_PASSWORD')
            
            if username and password:
                logger.info(f"Используем неинтерактивную аутентификацию для Terrascope")
                wc_mask, wc_profile, wc_path = load_worldcover_mask_by_coords(
                    bbox_wgs84, 
                    username=username, 
                    password=password
                )
                wc_mask_cropped = crop_and_resize_worldcover(wc_path, bbox_wgs84, (tile_size, tile_size), src_crs=src_crs)
            else:
                logger.warning("Terrascope учетные данные не найдены, создаем пустую маску")
                wc_mask_cropped = np.zeros((tile_size, tile_size), dtype=np.uint8)
        
        wc_mask_path = os.path.join(tile_dir, "worldcover_mask.png")
        h, w = wc_mask_cropped.shape
        rgb_mask = np.zeros((h, w, 3), dtype=np.uint8)
        for class_code in np.unique(wc_mask_cropped):
            category = code_to_category.get(int(class_code), "unknown")
            color = CATEGORY_COLORS.get(category, [128, 128, 128])
            rgb_mask[wc_mask_cropped == class_code] = color
        img = Image.fromarray(rgb_mask, mode='RGB')
        img.save(wc_mask_path)
        
        tasks = []
        for method in methods:
            for model in MODELS:
                tasks.append((tile_idx, x0, y0, tile_dir, tile_all, tile_ndvi, tci_path, wc_mask_cropped, method, model, wc_legend, code_to_category, category2code))
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(process_method_model_for_tile_method1, *args) for args in tasks]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f'Error in task: {e}')
        
        # Print API cost summary
        logger.info("Printing API cost summary...")
        print_cost_summary()

if __name__ == "__main__":
    main() 