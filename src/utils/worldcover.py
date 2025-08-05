import os
import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask
import geopandas as gpd
from shapely.geometry import box, shape
from terracatalogueclient import Catalogue
import glob
from matplotlib import pyplot as plt
from rasterio.windows import from_bounds
from skimage.transform import resize
from PIL import Image

def load_worldcover_mask_by_coords(coords, coords_format="bbox", output_path=None, product_type="urn:eop:VITO:ESA_WorldCover_10m_2021_V2", year="2021", download_dir="downloads", username=None, password=None):
    """
    Загружает маску WorldCover по координатам (bbox, geojson и др.).
    coords: bbox (list [min_lon, min_lat, max_lon, max_lat]) или geojson (dict)
    coords_format: "bbox" или "geojson"
    output_path: путь для сохранения результата (GeoTIFF), если нужно
    product_type: идентификатор коллекции (по умолчанию WorldCover 2021, 10m)
    year: год WorldCover (2020, 2021, ...)
    download_dir: папка для скачивания исходных файлов
    username, password: логин и пароль Terrascope для неинтерактивной аутентификации
    Возвращает: np.ndarray (маска), profile (метаданные rasterio), local_path (путь к tif)
    """
    # Проверяем, есть ли уже скачанный *_Map.tif
    map_files = glob.glob(os.path.join(download_dir, '**', '*_Map.tif'), recursive=True)
    if map_files:
        local_path = map_files[0]
        with rasterio.open(local_path) as src:
            mask = src.read(1)
            profile = src.profile
        if output_path:
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(mask, 1)
        return mask, profile, local_path
    # Если нет — скачиваем
    if username and password:
        cat = Catalogue().authenticate_non_interactive(username, password)
    else:
        cat = Catalogue().authenticate()
    if coords_format == "bbox":
        min_lon, min_lat, max_lon, max_lat = coords
        geometry = box(min_lon, min_lat, max_lon, max_lat)
    elif coords_format == "geojson":
        geometry = shape(coords["geometry"] if "geometry" in coords else coords)
    else:
        raise ValueError(f"Unsupported coords_format: {coords_format}")
    products = list(cat.get_products(product_type, geometry=geometry))
    if not products:
        raise RuntimeError("WorldCover product not found for given area!")
    cat.download_products(products, download_dir, force=True)
    # Ищем файл *_Map.tif в подпапках
    map_files = glob.glob(os.path.join(download_dir, '**', '*_Map.tif'), recursive=True)
    if not map_files:
        raise RuntimeError("No *_Map.tif files found in download directory!")
    local_path = map_files[0]
    with rasterio.open(local_path) as src:
        mask = src.read(1)
        profile = src.profile
    if output_path:
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(mask, 1)
    return mask, profile, local_path

# Легенда WorldCover 2021 (класс: (название, цвет RGB))
def get_worldcover_legend():
    return {
        10: ("Tree cover", (0, 100, 0)),
        20: ("Shrubland", (255, 187, 34)),
        30: ("Grassland", (255, 255, 76)),
        40: ("Cropland", (240, 150, 255)),
        50: ("Built-up", (250, 0, 0)),
        60: ("Bare / sparse vegetation", (180, 180, 180)),
        70: ("Snow and ice", (240, 240, 240)),
        80: ("Permanent water bodies", (0, 100, 200)),
        90: ("Herbaceous wetland", (0, 150, 160)),
        95: ("Mangroves", (0, 207, 117)),
        100: ("Moss and lichen", (250, 230, 160)),
    }

def compare_masks(mask_pred, mask_gt, legend=None):
    """
    Сравнивает две маски (предсказание и эталон) и возвращает метрики:
    - pixel accuracy (overall accuracy)
    - confusion matrix
    - IoU по классам
    - precision, recall, f1 по классам
    - mean IoU, weighted IoU
    - Cohen's kappa
    """
    from sklearn.metrics import confusion_matrix, cohen_kappa_score
    import numpy as np

    mask_pred = np.asarray(mask_pred).flatten()
    mask_gt = np.asarray(mask_gt).flatten()
    classes = sorted(set(np.unique(mask_pred)) | set(np.unique(mask_gt)))
    cm = confusion_matrix(mask_gt, mask_pred, labels=classes)
    pixel_acc = np.mean(mask_pred == mask_gt)
    iou = {}
    precision = {}
    recall = {}
    f1 = {}
    per_class = {}
    total_pixels = len(mask_gt)
    weighted_iou_sum = 0
    pixel_counts = {}

    for i, cls in enumerate(classes):
        tp = cm[i, i]
        fn = cm[i, :].sum() - tp
        fp = cm[:, i].sum() - tp
        tn = cm.sum() - (tp + fp + fn)
        denom_iou = tp + fp + fn
        denom_precision = tp + fp
        denom_recall = tp + fn
        # IoU
        iou_val = tp / denom_iou if denom_iou > 0 else 0.0
        iou[cls] = iou_val
        # Precision
        precision_val = tp / denom_precision if denom_precision > 0 else 0.0
        precision[cls] = precision_val
        # Recall
        recall_val = tp / denom_recall if denom_recall > 0 else 0.0
        recall[cls] = recall_val
        # F1
        if precision_val + recall_val > 0:
            f1_val = 2 * precision_val * recall_val / (precision_val + recall_val)
        else:
            f1_val = 0.0
        f1[cls] = f1_val
        # Pixel count for weighted IoU
        n_pixels = (mask_gt == cls).sum()
        pixel_counts[cls] = n_pixels
        weighted_iou_sum += iou_val * n_pixels
        # Сохраняем все метрики по классу
        per_class[cls] = {
            'iou': iou_val,
            'precision': precision_val,
            'recall': recall_val,
            'f1': f1_val,
            'pixels': n_pixels,
        }

    # Средний IoU (по всем классам)
    mean_iou = np.mean(list(iou.values())) if iou else 0.0
    # Взвешенный IoU (по количеству пикселей класса в эталоне)
    weighted_iou = weighted_iou_sum / total_pixels if total_pixels > 0 else 0.0
    # Cohen's kappa
    try:
        kappa = cohen_kappa_score(mask_gt, mask_pred, labels=classes)
    except Exception:
        kappa = 0.0

    return {
        'pixel_accuracy': pixel_acc,
        'overall_accuracy': pixel_acc,
        'confusion_matrix': cm,
        'classes': classes,
        'iou': iou,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'mean_iou': mean_iou,
        'weighted_iou': weighted_iou,
        'kappa': kappa,
        'per_class': per_class,
        'pixel_counts': pixel_counts,
    }

def plot_mask(mask, legend=None, title=None, save_path=None):
    """
    Визуализирует маску с использованием цветов из легенды WorldCover.
    legend: dict (класс: (название, (R,G,B)))
    """
    if legend is None:
        legend = get_worldcover_legend()
    # Создаём RGB-изображение
    rgb = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for cls, (_, color) in legend.items():
        rgb[mask == cls] = color
    plt.figure(figsize=(6, 6))
    plt.imshow(rgb)
    plt.axis('off')
    if title:
        plt.title(title)
    # Добавляем легенду
    import matplotlib.patches as mpatches
    patches = [mpatches.Patch(color=np.array(color)/255, label=f"{cls}: {name}") for cls, (name, color) in legend.items() if np.any(mask == cls)]
    if patches:
        plt.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc='upper left')
    if save_path:
        plt.savefig(save_path, bbox_inches='tight')
    plt.show()

def crop_and_resize_worldcover(worldcover_path, bbox_wgs84, out_shape, src_crs=None):
    """
    Crops and resizes a WorldCover image to match the specified bounding box and output shape.
    Args:
        worldcover_path: Path to the WorldCover GeoTIFF
        bbox_wgs84: Bounding box in WGS84 coordinates (min_lon, min_lat, max_lon, max_lat)
        out_shape: Desired output shape (height, width)
        src_crs: Source CRS of the satellite imagery (e.g., from B02)
    Returns:
        np.ndarray: Cropped and resized WorldCover mask
    """
    try:
        with rasterio.open(worldcover_path) as src:
            # If src_crs provided, transform bbox from that CRS to WorldCover CRS
            if src_crs:
                bbox_src = rasterio.warp.transform_bounds(src_crs, src.crs, *bbox_wgs84)
            else:
                bbox_src = bbox_wgs84
            # Get window from bounds
            window = from_bounds(*bbox_src, transform=src.transform)
            # Read window
            mask = src.read(1, window=window)
            
            # Проверяем, что маска не пустая и имеет валидные размеры
            if mask.size == 0 or np.all(mask == 0):
                print(f"Warning: Empty or zero mask from {worldcover_path}")
                # Возвращаем пустую маску нужного размера
                return np.zeros(out_shape, dtype=np.uint8)
            
            # Проверяем размеры для resize
            if any(s <= 0 for s in out_shape):
                print(f"Warning: Invalid output shape {out_shape}")
                return np.zeros(out_shape, dtype=np.uint8)
            
            # Resize to match out_shape (using nearest neighbor resampling to preserve class values)
            mask_resized = resize(mask, out_shape, order=0, preserve_range=True, anti_aliasing=False).astype(mask.dtype)
            return mask_resized
    except Exception as e:
        print(f"Error in crop_and_resize_worldcover: {e}")
        # Возвращаем пустую маску нужного размера в случае ошибки
        return np.zeros(out_shape, dtype=np.uint8)

def save_worldcover_mask_png(mask, out_path):
    """
    Сохраняет маску WorldCover (2D, коды классов) в PNG с официальными цветами ESA.
    mask: np.ndarray (h, w), значения — коды классов (10, 20, ...)
    out_path: путь для сохранения PNG
    """
    legend = get_worldcover_legend()
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for code, (_, color) in legend.items():
        rgb[mask == code] = color
    Image.fromarray(rgb, mode='RGB').save(out_path)
