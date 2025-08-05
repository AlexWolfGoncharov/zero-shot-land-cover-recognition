"""
clustering_methods.py

Единый интерфейс для всех методов кластеризации спутниковых изображений.
Каждая функция принимает numpy-массив изображения (tile), параметры метода и возвращает:
- mask: np.ndarray (H, W) — карта кластеров
- color_map: np.ndarray (H, W, 3) — цветовая карта кластеров (RGB)
- cluster_info: dict — описание соответствия цветов/кластеров
- masks_by_cluster: dict[int, np.ndarray] — бинарные маски по каждому кластеру
"""
import numpy as np
import traceback
from sklearn.cluster import KMeans, DBSCAN
from skimage.segmentation import slic, watershed
from skimage.util import img_as_float
from skimage.filters import sobel, threshold_otsu
from skimage.feature import peak_local_max
from skimage.color import rgb2gray
from scipy import ndimage as ndi
import gc
try:
    from minisom import MiniSom
except ImportError:
    MiniSom = None
import torch
import torch.nn as nn
import torch.nn.functional as F

def cluster_kmeans(tiles, n_clusters: int = 6, **kwargs):
    """KMeans-кластеризация."""
    # Обработка одиночного тайла
    if isinstance(tiles, np.ndarray):
        tiles = [tiles]
    
    results = []
    for tile in tiles:
        # Приводим к (H, W, C)
        if len(tile.shape) == 3 and tile.shape[0] < tile.shape[1] and tile.shape[0] < tile.shape[2]:
            tile = np.moveaxis(tile, 0, -1)  # (C, H, W) -> (H, W, C)
        
        h, w = tile.shape[:2]
        if len(tile.shape) == 3:
            c = tile.shape[2]
            print(f"[DEBUG] KMeans clustering: using {c} channels (shape: {tile.shape})")
            flat = tile.reshape(-1, c)
        else:
            flat = tile.reshape(-1, 1)
        
        # Применяем KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(flat)
        mask = labels.reshape(h, w)
        
        # Генерируем цветовую карту
        colors = np.random.randint(0, 255, (n_clusters, 3), dtype=np.uint8)
        color_map = colors[mask]
        cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters)}
        masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters)}
        
        results.append((mask, color_map, cluster_info, masks_by_cluster))
    
    # Возвращаем результаты для каждого тайла или первый результат, если был один тайл
    if len(results) == 1:
        return results[0]
    return results

def cluster_dbscan(tile: np.ndarray, eps: float = 0.3, min_samples: int = 10, **kwargs):
    """DBSCAN-кластеризация."""
    # Приводим к (H, W, C)
    if tile.shape[0] < tile.shape[-1]:
        tile = np.moveaxis(tile, 0, -1)
    h, w, c = tile.shape
    flat = tile.reshape(-1, c)
    db = DBSCAN(eps=eps, min_samples=min_samples, **kwargs)
    labels = db.fit_predict(flat)
    mask = labels.reshape(h, w)
    # Генерируем цветовую карту
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    colors = np.random.randint(0, 255, (n_clusters+1, 3), dtype=np.uint8)
    color_map = colors[np.clip(mask, 0, n_clusters)]
    cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters+1)}
    masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters+1)}
    return mask, color_map, cluster_info, masks_by_cluster

def cluster_slic(tile: np.ndarray, n_segments: int = 100, compactness: float = 10.0, **kwargs):
    """SLIC-суперпиксели."""
    # Приводим к (H, W, C)
    if tile.shape[0] < tile.shape[-1]:
        tile = np.moveaxis(tile, 0, -1)
    image = img_as_float(tile)
    mask = slic(image, n_segments=n_segments, compactness=compactness, start_label=0, channel_axis=-1, **kwargs)
    n_clusters = mask.max() + 1
    colors = np.random.randint(0, 255, (n_clusters, 3), dtype=np.uint8)
    color_map = colors[mask]
    cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters)}
    masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters)}
    return mask, color_map, cluster_info, masks_by_cluster

def cluster_watershed(tile: np.ndarray, n_markers: int = 100, compactness: float = 0.0, **kwargs):
    """Watershed-сегментация."""
    # Handle list of tiles
    if isinstance(tile, list):
        if len(tile) == 1:
            tile = tile[0]
        else:
            results = []
            for t in tile:
                results.append(cluster_watershed(t, n_markers, compactness, **kwargs))
            return results
            
    # Приводим к (H, W, C)
    if tile.shape[0] < tile.shape[-1]:
        tile = np.moveaxis(tile, 0, -1)
    image = img_as_float(tile)
    # Для маркеров используем максимум по градиенту (или максимум по интенсивности)
    if image.shape[2] > 1:
        gray = np.mean(image, axis=2)
    else:
        gray = image[..., 0]
    gradient = sobel(gray)
    # Маркеры — локальные максимумы
    markers = np.zeros_like(gray, dtype=int)
    coords = peak_local_max(gray, num_peaks=n_markers, exclude_border=False)
    for i, (y, x) in enumerate(coords):
        markers[y, x] = i + 1
    mask = watershed(gradient, markers=markers, compactness=compactness, **kwargs)
    n_clusters = mask.max() + 1
    colors = np.random.randint(0, 255, (n_clusters, 3), dtype=np.uint8)
    color_map = colors[mask]
    cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters)}
    masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters)}
    return mask, color_map, cluster_info, masks_by_cluster

def cluster_som(tiles, n_clusters: int = 6, som_x: int = 8, som_y: int = 8, sigma: float = 1.0, learning_rate: float = 0.5, random_seed: int = 42, **kwargs):
    """Self-Organizing Map (SOM) кластеризация."""
    if MiniSom is None:
        raise ImportError("Для SOM-кластеризации требуется пакет minisom. Установите его: pip install minisom")
    
    # Обработка одиночного тайла
    if isinstance(tiles, np.ndarray):
        tiles = [tiles]
    
    results = []
    for tile in tiles:
        # Приводим к (H, W, C)
        if len(tile.shape) == 3 and tile.shape[0] < tile.shape[1] and tile.shape[0] < tile.shape[2]:
            tile = np.moveaxis(tile, 0, -1)  # (C, H, W) -> (H, W, C)
        
        h, w = tile.shape[:2]
        if len(tile.shape) == 3:
            c = tile.shape[2]
            flat = tile.reshape(-1, c)
        else:
            c = 1
            flat = tile.reshape(-1, 1)
            
        som = MiniSom(som_x, som_y, c, sigma=sigma, learning_rate=learning_rate, random_seed=random_seed)
        som.random_weights_init(flat)
        som.train(flat, 100)
        
        # Для каждого пикселя ищем ближайший нейрон
        win_map = np.array([som.winner(x) for x in flat])
        
        # Кластеры по координате нейрона
        cluster_labels = win_map[:,0] * som_y + win_map[:,1]
        
        # Опционально: можно уменьшить число кластеров через KMeans поверх SOM-нейронов
        if n_clusters < som_x * som_y:
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=n_clusters, random_state=random_seed, n_init=10)
            cluster_labels = kmeans.fit_predict(win_map)
            
        mask = cluster_labels.reshape(h, w)
        n_clusters_actual = mask.max() + 1
        colors = np.random.randint(0, 255, (n_clusters_actual, 3), dtype=np.uint8)
        color_map = colors[mask]
        cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters_actual)}
        masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters_actual)}
        
        results.append((mask, color_map, cluster_info, masks_by_cluster))
    
    # Возвращаем результаты для каждого тайла или первый результат, если был один тайл
    if len(results) == 1:
        return results[0]
    return results

def cluster_unet(tiles, n_clusters: int = 6, encoder=None, device="cpu", **kwargs):
    """U-Net encoder feature clustering."""
    # Обработка одиночного тайла
    if isinstance(tiles, np.ndarray):
        tiles = [tiles]
    
    results = []
    for tile in tiles:
        # Приводим к (H, W, C)
        if len(tile.shape) == 3 and tile.shape[0] < tile.shape[1] and tile.shape[0] < tile.shape[2]:
            tile = np.moveaxis(tile, 0, -1)  # (C, H, W) -> (H, W, C)
        
        h, w = tile.shape[:2]
        if len(tile.shape) == 3:
            c = tile.shape[2]
        else:
            # Добавляем канал для одноканального изображения
            tile = tile[..., np.newaxis]
            c = 1
            
        # Преобразуем в torch.Tensor и нормализуем
        x = torch.from_numpy(tile.astype(np.float32)).permute(2, 0, 1).unsqueeze(0) / 255.0
        
        if encoder is None:
            raise ValueError("encoder (U-Net encoder) должен быть передан явно!")
            
        with torch.no_grad():
            # UNetEncoder возвращает кортеж из 3 тензоров, используем все
            encoder_output = encoder(x.to(device))
            if isinstance(encoder_output, tuple):
                x1, x2, x3 = encoder_output
                # Апсемплим x2, x3 до размера x1
                x2_up = F.interpolate(x2, size=x1.shape[2:], mode='bilinear', align_corners=False)
                x3_up = F.interpolate(x3, size=x1.shape[2:], mode='bilinear', align_corners=False)
                # Конкатенируем признаки
                feats = torch.cat([x1, x2_up, x3_up], dim=1).cpu().squeeze(0)  # (F, H, W)
            else:
                feats = encoder_output.cpu().squeeze(0)  # (F, H, W)
            
        feats = feats.permute(1, 2, 0).reshape(-1, feats.shape[0])  # (H*W, F)
        
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(feats)
        
        mask = labels.reshape(h, w)
        n_clusters_actual = mask.max() + 1
        colors = np.random.randint(0, 255, (n_clusters_actual, 3), dtype=np.uint8)
        color_map = colors[mask]
        cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters_actual)}
        masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters_actual)}
        
        results.append((mask, color_map, cluster_info, masks_by_cluster))
    
    # Возвращаем результаты для каждого тайла или первый результат, если был один тайл
    if len(results) == 1:
        return results[0]
    return results

# Можно добавить другие методы по аналогии

# Универсальный интерфейс для кластеризации

def cluster_tiles_kmeans(tiles: list, n_clusters: int = 5, random_state: int = 42) -> list:
    """
    Кластеризация массива тайлов с помощью KMeans.
    :param tiles: список np.ndarray (C, H, W) или (H, W, C)
    :param n_clusters: число кластеров
    :return: список np.ndarray (H, W) — маски кластеров
    """
    masks = []
    for tile in tiles:
        # Приводим к (H, W, C)
        if tile.shape[0] < tile.shape[-1]:
            tile = np.moveaxis(tile, 0, -1)  # (C, H, W) -> (H, W, C)
        h, w, c = tile.shape
        flat = tile.reshape(-1, c)
        kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
        labels = kmeans.fit_predict(flat)
        mask = labels.reshape(h, w)
        masks.append(mask)
    return masks

# Универсальный интерфейс (расширяется для других методов)
def cluster_tiles(images, method='kmeans', **kwargs):
    """
    Выполняет кластеризацию для списка изображений выбранным методом.
    
    Parameters
    ----------
    images : list of np.ndarray or np.ndarray
        Список изображений для кластеризации или одно изображение
    method : str
        Метод кластеризации: 'kmeans', 'dbscan', 'slic', 'watershed', 'watershed_kmeans', 'watershed_ndvi', 'som', 'unet'
    **kwargs : dict
        Дополнительные параметры для метода кластеризации
        
    Returns
    -------
    dict
        Словарь с результатами кластеризации:
        - 'mask': np.ndarray - маска кластеров
        - 'colors': np.ndarray - цвета для визуализации кластеров
        - 'cluster_info': dict - информация о кластерах
        - 'binary_masks': dict - бинарные маски для каждого кластера
    """
    # Проверяем, является ли images одиночным массивом numpy или списком
    if isinstance(images, np.ndarray):
        if len(images.shape) > 2:
            # (C, H, W) формат
            images = [images]
        else:
            # (H, W, C) формат или (H, W)
            images = [images]
    
    # Словарь методов кластеризации
    methods = {
        'kmeans': cluster_kmeans,
        'dbscan': cluster_dbscan,
        'slic': cluster_slic,
        'watershed': cluster_watershed,
        'watershed_kmeans': cluster_watershed_kmeans,
        'watershed_ndvi': cluster_watershed_ndvi,
        'som': cluster_som,
        'unet': cluster_unet,
        'unet_encoder_kmeans': cluster_unet_encoder_kmeans,  # Новый метод
    }
    
    if method not in methods:
        raise ValueError(f"Неизвестный метод кластеризации: {method}. Доступные методы: {list(methods.keys())}")
    
    # U-Net требует передачи энкодера
    if method == 'unet' and 'encoder' not in kwargs:
        raise ValueError("Для метода 'unet' необходимо передать энкодер (U-Net encoder) явно через параметр 'encoder'")
    
    try:
        # Применяем выбранный метод кластеризации
        if method in methods:
            results = methods[method](images, **kwargs)
            
            # Проверка на формат результатов
            if isinstance(results, tuple):
                # Если вернулся кортеж (маска, цвета, инфо о кластерах)
                if len(results) >= 3:
                    mask, colors, cluster_info = results[:3]
                    binary_masks = results[3] if len(results) > 3 else []
                    results = {
                        "mask": mask,
                        "colors": colors,
                        "cluster_info": cluster_info,
                        "binary_masks": binary_masks
                    }
            elif isinstance(results, list):
                # Если это список результатов для нескольких изображений
                processed_results = []
                for res in results:
                    if isinstance(res, dict):
                        # Уже в нужном формате
                        processed_results.append(res)
                    elif isinstance(res, tuple):
                        # Конвертируем кортеж в словарь
                        if len(res) >= 3:
                            mask, colors, cluster_info = res[:3]
                            binary_masks = res[3] if len(res) > 3 else []
                            processed_results.append({
                                "mask": mask,
                                "colors": colors,
                                "cluster_info": cluster_info,
                                "binary_masks": binary_masks
                            })
                results = processed_results
                
                # Если был передан только один образ, возвращаем только первый результат
                if len(images) == 1 and len(processed_results) == 1:
                    results = processed_results[0]
            
        return results
    except Exception as e:
        print(f"Ошибка при применении метода {method}: {str(e)}")
        traceback.print_exc()
        return {
            "mask": np.zeros((images[0].shape[0], images[0].shape[1]), dtype=np.uint8),
            "colors": {},
            "cluster_info": {},
            "binary_masks": []
        }

def normalize_tile(tile):
    tile = tile.astype(np.float32)
    for c in range(tile.shape[0]):
        ch = tile[c]
        tile[c] = (ch - ch.min()) / (ch.max() - ch.min() + 1e-6)
    return tile

def compute_informative_features(tile_dict):
    nir = tile_dict["B8A"].astype(np.float32)
    red = tile_dict["B04"].astype(np.float32)
    ndvi = (nir - red) / (nir + red + 1e-6)
    green = tile_dict["B03"].astype(np.float32)
    swir = tile_dict["B11"].astype(np.float32)
    ndwi = (green - swir) / (green + swir + 1e-6)
    ndbi = (swir - nir) / (swir + nir + 1e-6)
    brightness = np.mean([tile_dict["B02"], tile_dict["B03"], tile_dict["B04"]], axis=0)
    feats = np.stack([ndvi, ndwi, ndbi, brightness], axis=-1)
    feats_norm = (feats - feats.min(axis=(0,1))) / (feats.max(axis=(0,1)) - feats.min(axis=(0,1)) + 1e-6)
    return feats_norm

def dbscan_clustering(X, eps=0.2, min_samples=5, sample_size=10000, auto_eps=False):
    from sklearn.cluster import DBSCAN
    from sklearn.neighbors import NearestNeighbors
    n_points = X.shape[0]
    idx = np.arange(n_points)
    if n_points > sample_size:
        idx = np.random.choice(n_points, sample_size, replace=False)
    X_sample = X[idx]
    if auto_eps:
        neigh = NearestNeighbors(n_neighbors=min_samples)
        nbrs = neigh.fit(X_sample)
        distances, _ = nbrs.kneighbors(X_sample)
        k_distances = np.sort(distances[:, -1])
        eps = np.percentile(k_distances, 95)
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(X_sample)
    mask = -np.ones(n_points, dtype=int)
    mask[idx] = db.labels_
    return mask

def cluster_dbscan_advanced(tile, tile_dict=None, variant='norm', eps=0.2, min_samples=5, sample_size=10000, auto_eps=False):
    """
    Универсальный интерфейс DBSCAN:
    variant: 'norm' — по всем каналам с нормализацией
             'auto_eps' — eps подбирается автоматически
             'informative' — только информативные признаки (NDVI, NDWI, NDBI, яркость)
    tile_dict: нужен для informative
    Возвращает mask (H, W)
    """
    if variant == 'norm' or variant == 'auto_eps':
        tile_norm = normalize_tile(tile.copy())
        X = tile_norm.reshape(tile_norm.shape[0], -1).T
        mask = dbscan_clustering(X, eps=eps, min_samples=min_samples, sample_size=sample_size, auto_eps=(variant=='auto_eps'))
        mask = mask.reshape(tile.shape[1:])
        gc.collect()
        return mask
    elif variant == 'informative':
        if tile_dict is None:
            raise ValueError('tile_dict is required for informative DBSCAN')
        feats_norm = compute_informative_features(tile_dict)
        X = feats_norm.reshape(-1, feats_norm.shape[-1])
        mask = dbscan_clustering(X, eps=eps, min_samples=min_samples, sample_size=sample_size, auto_eps=False)
        mask = mask.reshape(tile.shape[1], tile.shape[2])
        gc.collect()
        return mask
    else:
        raise ValueError(f'Unknown DBSCAN variant: {variant}')

# Пример использования:
# mask = cluster_dbscan_advanced(tile, tile_dict, variant='informative')

def cluster_watersheds(images, eps=10, min_samples=5, n_segments=50, mask_type='binary', **kwargs):
    """Кластеризация с помощью алгоритма watershed с предварительной сегментацией маркеров."""
    results = []
    for i, img in enumerate(images):
        # Предварительная обработка изображения
        img_gray = rgb2gray(img) if img.shape[-1] == 3 else img
        
        # Рассчитываем градиент
        gradient = sobel(img_gray)
        
        # Находим маркеры
        markers = np.zeros_like(img_gray, dtype=np.uint8)
        thresh_low = threshold_otsu(img_gray) * 0.5
        thresh_high = threshold_otsu(img_gray) * 1.5
        markers[img_gray < thresh_low] = 1
        markers[img_gray > thresh_high] = 2
        
        # Применяем watershed
        mask = watershed(gradient, markers, mask=None)
        
        # Создаем дополнительные бинарные маски для каждого кластера
        unique_labels = np.unique(mask)
        binary_masks = []
        for label in unique_labels:
            binary_mask = (mask == label).astype(np.uint8)
            binary_masks.append(binary_mask)
        
        # Создаем словарь с результатами
        colors = {int(i): list(np.random.randint(0, 255, 3)) for i in range(len(unique_labels))}
        cluster_info = {int(i): {"count": np.sum(mask == label), "centroid": None} for i, label in enumerate(unique_labels)}
        
        results.append({
            "mask": mask.astype(np.uint8),
            "colors": colors,
            "cluster_info": cluster_info,
            "binary_masks": binary_masks
        })
        
    return results

def cluster_watershed_kmeans(images, n_clusters=10, **kwargs):
    """KMeans кластеризация с последующим применением watershed."""
    if isinstance(images, np.ndarray):
        images = [images]
        
    results = []
    for img in images:
        # Приводим к (H, W, C)
        if len(img.shape) == 3 and img.shape[0] < img.shape[1] and img.shape[0] < img.shape[2]:
            img = np.moveaxis(img, 0, -1)  # (C, H, W) -> (H, W, C)
            
        # Преобразуем к RGB для rgb2gray, если много каналов
        if len(img.shape) == 3 and img.shape[2] > 3:
            # Используем первые три канала или среднее по всем каналам
            img_rgb = img[..., :3] if img.shape[2] >= 3 else np.mean(img, axis=2, keepdims=True)
        else:
            img_rgb = img
            
        if len(img.shape) == 3:
            h, w, c = img.shape
            img_flat = img.reshape(-1, c)
        else:
            h, w = img.shape
            img_flat = img.reshape(-1, 1)
        
        # Применяем KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(img_flat)
        mask_kmeans = labels.reshape(h, w)
        
        # Создаем маркеры из KMeans
        markers = mask_kmeans + 1  # Оставляем первый маркер для фона
        
        # Используем градиент для watershed
        if len(img_rgb.shape) == 3 and img_rgb.shape[2] == 3:
            img_gray = rgb2gray(img_rgb)
        elif len(img_rgb.shape) == 3 and img_rgb.shape[2] == 1:
            img_gray = img_rgb[..., 0]
        else:
            img_gray = img_rgb
            
        # Рассчитываем градиент
        gradient = sobel(img_gray)
        
        # Применяем watershed с KMeans маркерами
        mask = watershed(gradient, markers)
        
        # Создаем бинарные маски
        unique_labels = np.unique(mask)
        binary_masks = []
        for label in unique_labels:
            binary_mask = (mask == label).astype(np.uint8)
            binary_masks.append(binary_mask)
        
        # Создаем словарь с результатами
        colors = {int(i): list(np.random.randint(0, 255, 3)) for i in range(len(unique_labels))}
        cluster_info = {int(i): {"count": np.sum(mask == label), "centroid": None} for i, label in enumerate(unique_labels)}
        
        results.append({
            "mask": mask.astype(np.uint8),
            "colors": colors,
            "cluster_info": cluster_info,
            "binary_masks": binary_masks
        })
    
    if len(results) == 1:
        return results[0]
    return results

def cluster_watershed_ndvi(images, n_thresholds=3, **kwargs):
    """Кластеризация с watershed, используя NDVI для определения маркеров."""
    if isinstance(images, np.ndarray):
        images = [images]
        
    results = []
    
    for img in images:
        # Приводим к (H, W, C)
        if len(img.shape) == 3 and img.shape[0] < img.shape[1] and img.shape[0] < img.shape[2]:
            img = np.moveaxis(img, 0, -1)  # (C, H, W) -> (H, W, C)
            
        if len(img.shape) == 3 and img.shape[2] >= 4:  # Убедимся, что у нас есть NIR и RED для NDVI
            # Индексы каналов Sentinel-2
            # B02 (Blue): 0, B03 (Green): 1, B04 (Red): 2, B8A (NIR): 3, B11 (SWIR): 4, B12 (SWIR): 5
            nir_idx = 3  # B8A (NIR)
            red_idx = 2   # B04 (Red)
            
            # Если у нас 9 каналов, то это полный набор Sentinel-2
            if img.shape[2] == 9:
                print(f"Обнаружены все 9 каналов Sentinel-2, используем B8A (NIR) и B04 (Red) для NDVI")
            else:
                print(f"Используем индекс {nir_idx} для NIR и {red_idx} для Red")
            
            # Извлекаем каналы NIR и RED
            if img.shape[2] > nir_idx and img.shape[2] > red_idx:
                nir = img[..., nir_idx].astype(float)
                red = img[..., red_idx].astype(float)
            else:
                # Если не хватает каналов, берем последний и предпоследний
                print(f"Недостаточно каналов для NIR и RED, используем доступные каналы")
                nir = img[..., -1].astype(float)
                red = img[..., -2].astype(float)
            
            # Вычисляем NDVI, избегая деления на ноль
            epsilon = 1e-10
            ndvi = np.zeros_like(nir)
            valid_mask = (nir + red) > epsilon
            ndvi[valid_mask] = (nir[valid_mask] - red[valid_mask]) / (nir[valid_mask] + red[valid_mask])
            
            # Нормализуем NDVI от 0 до 1
            ndvi_norm = (ndvi + 1) / 2
            
            # Создаем маркеры на основе более информативного разбиения NDVI
            markers = np.zeros_like(ndvi, dtype=np.int32)
            
            # Используем квантили вместо равномерных интервалов для лучшей сегментации
            quantiles = np.linspace(0, 1, n_thresholds+1)
            thresholds = [np.quantile(ndvi_norm, q) for q in quantiles]
            
            # Добавляем небольшую вариацию к порогам, если они слишком близки
            min_diff = 0.05  # Минимальная разница между порогами
            for i in range(1, len(thresholds)):
                if thresholds[i] - thresholds[i-1] < min_diff:
                    thresholds[i] = min(thresholds[i-1] + min_diff, 1.0)
            
            # Применяем пороги с некоторым перекрытием
            for i in range(1, len(thresholds)):
                markers[(ndvi_norm >= thresholds[i-1] * 0.9) & (ndvi_norm < thresholds[i] * 1.1)] = i
            
            # Убедимся, что у нас есть хотя бы n_thresholds уникальных меток
            if len(np.unique(markers)) < n_thresholds:
                print(f"Предупреждение: создано только {len(np.unique(markers))} уникальных меток вместо {n_thresholds}")
                # Создаем дополнительные маркеры на основе интенсивности
                if np.unique(markers).size == 1:  # Если все пиксели в одном кластере
                    # Используем K-means для создания дополнительных кластеров
                    from sklearn.cluster import KMeans
                    # Используем первые три канала для кластеризации
                    rgb = img[..., :3] if img.shape[2] >= 3 else img
                    rgb_flat = rgb.reshape(-1, rgb.shape[-1])
                    kmeans = KMeans(n_clusters=n_thresholds, random_state=42, n_init=10)
                    cluster_labels = kmeans.fit_predict(rgb_flat)
                    markers = cluster_labels.reshape(img.shape[:2])
                    
            # Применяем watershed
            # Для градиента используем NDVI как базовую метрику
            gradient = sobel(ndvi_norm)
            mask = watershed(gradient, markers)
            
            # Создаем бинарные маски
            unique_labels = np.unique(mask)
            binary_masks = []
            for label in unique_labels:
                binary_mask = (mask == label).astype(np.uint8)
                binary_masks.append(binary_mask)
            
            # Создаем словарь с результатами
            colors = {int(i): list(np.random.randint(0, 255, 3)) for i in range(len(unique_labels))}
            cluster_info = {int(i): {"count": np.sum(mask == label), "centroid": None} for i, label in enumerate(unique_labels)}
            
            results.append({
                "mask": mask.astype(np.uint8),
                "colors": colors,
                "cluster_info": cluster_info,
                "binary_masks": binary_masks
            })
        else:
            print(f"Недостаточно каналов для расчета NDVI: {img.shape}")
            # Возвращаем просто сегментацию на основе интенсивности
            if len(img.shape) == 3 and img.shape[2] == 3:
                img_gray = rgb2gray(img)
            elif len(img.shape) == 3:
                img_gray = np.mean(img, axis=2)
            else:
                img_gray = img
                
            # Используем K-means для создания наборов маркеров
            from sklearn.cluster import KMeans
            img_flat = img.reshape(-1, img.shape[-1])
            kmeans = KMeans(n_clusters=n_thresholds, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(img_flat)
            markers = cluster_labels.reshape(img.shape[:2]) + 1
            
            gradient = sobel(img_gray)
            mask = watershed(gradient, markers)
            
            # Создаем бинарные маски
            unique_labels = np.unique(mask)
            binary_masks = []
            for label in unique_labels:
                binary_mask = (mask == label).astype(np.uint8)
                binary_masks.append(binary_mask)
            
            # Создаем словарь с результатами
            colors = {int(i): list(np.random.randint(0, 255, 3)) for i in range(len(unique_labels))}
            cluster_info = {int(i): {"count": np.sum(mask == label), "centroid": None} for i, label in enumerate(unique_labels)}
            
            results.append({
                "mask": mask.astype(np.uint8),
                "colors": colors,
                "cluster_info": cluster_info,
                "binary_masks": binary_masks
            })
    
    if len(results) == 1:
        return results[0]
    return results

# --- U-Net Encoder ---
class UNetEncoder(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.enc1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, 3, padding=1), nn.ReLU(),
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU()
        )
        self.pool1 = nn.MaxPool2d(2)
        self.enc2 = nn.Sequential(
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1), nn.ReLU()
        )
        self.pool2 = nn.MaxPool2d(2)
        self.enc3 = nn.Sequential(
            nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(),
            nn.Conv2d(128, 128, 3, padding=1), nn.ReLU()
        )
    def forward(self, x):
        x1 = self.enc1(x)
        x2 = self.enc2(self.pool1(x1))
        x3 = self.enc3(self.pool2(x2))
        return x1, x2, x3


def cluster_unet_encoder_kmeans(images, n_clusters=10, device="cpu"):
    """
    Кластеризация признаков UNet encoder (3 уровня + объединённые) по стеку каналов + NDVI + NDBI.
    images: list с каналами или dict с каналами (ключи: 'B02', ..., 'B12')
    Возвращает: mask, color_map, cluster_info, masks_by_cluster
    """
    # Проверяем тип входных данных
    if isinstance(images, list):
        if len(images) == 1:
            # Если передан список с одним элементом, берем его
            tile_data = images[0]
        else:
            # Если несколько изображений, берем первое
            print(f"[WARNING] Получено {len(images)} изображений, используем первое")
            tile_data = images[0]
    elif isinstance(images, dict):
        tile_data = images
    else:
        # Если передан numpy массив
        tile_data = images
    
    # Если tile_data - это numpy массив, конвертируем его в нужный формат
    if isinstance(tile_data, np.ndarray):
        if len(tile_data.shape) == 3:
            # (C, H, W) формат - конвертируем в словарь каналов
            bands = ["B02", "B03", "B04", "B05", "B06", "B07", "B8A", "B11", "B12"]
            tile_dict = {}
            for i, band in enumerate(bands[:tile_data.shape[0]]):
                tile_dict[band] = tile_data[i]
        else:
            raise ValueError(f"Неподдерживаемый формат данных: {tile_data.shape}")
    else:
        tile_dict = tile_data
    
    bands = ["B02", "B03", "B04", "B05", "B06", "B07", "B8A", "B11", "B12"]
    
    # Проверяем наличие всех каналов
    missing_bands = [b for b in bands if b not in tile_dict.keys()]
    if missing_bands:
        print(f"[WARNING] Отсутствуют каналы: {missing_bands}")
        available_bands = [b for b in bands if b in tile_dict.keys()]
        print(f"[INFO] Используем доступные каналы: {available_bands}")
        bands = available_bands
    
    tile_channels = [tile_dict[b] for b in bands if b in tile_dict.keys()]
    
    # Проверяем размеры каналов
    if not tile_channels:
        raise ValueError("Нет доступных каналов для обработки!")
    
    print(f"[DEBUG] Количество каналов: {len(tile_channels)}")
    print(f"[DEBUG] Размер первого канала: {tile_channels[0].shape}")
    
    # Нормализация каналов в диапазон [0, 1]
    tile_channels = [np.clip(ch.astype(np.float32) / 255.0, 0, 1) for ch in tile_channels]
    
    # NDVI - нормализуем в [0, 1] вместо [-1, 1]
    if "B8A" in tile_dict.keys() and "B04" in tile_dict.keys():
        nir = tile_dict["B8A"].astype(np.float32)
        red = tile_dict["B04"].astype(np.float32)
        ndvi = (nir - red) / (nir + red + 1e-6)
        ndvi = np.clip((ndvi + 1) / 2, 0, 1)  # Нормализация NDVI в [0, 1]
        tile_channels.append(ndvi)
        print(f"[DEBUG] Добавлен NDVI, размер: {ndvi.shape}")
    
    # NDBI - нормализуем в [0, 1] вместо [-1, 1]
    if "B11" in tile_dict.keys() and "B8A" in tile_dict.keys():
        swir = tile_dict["B11"].astype(np.float32)
        nir = tile_dict["B8A"].astype(np.float32)
        ndbi = (swir - nir) / (swir + nir + 1e-6)
        ndbi = np.clip((ndbi + 1) / 2, 0, 1)  # Нормализация NDBI в [0, 1]
        tile_channels.append(ndbi)
        print(f"[DEBUG] Добавлен NDBI, размер: {ndbi.shape}")
    
    # Собираем стек каналов
    tile_stack = np.stack(tile_channels, axis=0)  # (C, H, W)
    print(f"[DEBUG] Размер tile_stack: {tile_stack.shape}")
    
    # Проверяем, что данные не пустые
    if np.any(np.isnan(tile_stack)) or np.any(np.isinf(tile_stack)):
        print("[WARNING] Обнаружены NaN или Inf значения, заменяем на 0")
        tile_stack = np.nan_to_num(tile_stack, nan=0.0, posinf=1.0, neginf=0.0)
    
    encoder = UNetEncoder(in_channels=tile_stack.shape[0])
    encoder = encoder.to(device)
    encoder.eval()
    
    with torch.no_grad():
        x = torch.from_numpy(tile_stack).unsqueeze(0).to(device).float()
        print(f"[DEBUG] Размер входного тензора: {x.shape}")
        
        x1, x2, x3 = encoder(x)
        print(f"[DEBUG] Размеры признаков: x1={x1.shape}, x2={x2.shape}, x3={x3.shape}")
        
        # Апсемплим x2, x3 до размера x1
        x2_up = F.interpolate(x2, size=x1.shape[2:], mode='bilinear', align_corners=False)
        x3_up = F.interpolate(x3, size=x1.shape[2:], mode='bilinear', align_corners=False)
        
        # Конкатенируем признаки
        fmap_all = torch.cat([x1, x2_up, x3_up], dim=1).squeeze(0).cpu().numpy()  # (C_total, H, W)
        print(f"[DEBUG] Размер объединенных признаков: {fmap_all.shape}")
        
        # Добавляем пространственные координаты для лучшей сегментации
        H, W = fmap_all.shape[1:]
        y_coords, x_coords = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
        spatial_features = np.stack([x_coords / W, y_coords / H], axis=0)  # Нормализованные координаты
        fmap_all = np.concatenate([fmap_all, spatial_features], axis=0)
        print(f"[DEBUG] Размер с пространственными признаками: {fmap_all.shape}")
    
    # Кластеризация с оптимизацией
    H, W = fmap_all.shape[1:]
    fmap_all_flat = fmap_all.reshape(fmap_all.shape[0], -1).T  # [H*W, C_total]
    print(f"[DEBUG] Размер плоских признаков: {fmap_all_flat.shape}")
    
    # Сэмплируем данные для ускорения кластеризации
    n_samples = min(30000, fmap_all_flat.shape[0])  # Уменьшили до 30k пикселей
    if fmap_all_flat.shape[0] > n_samples:
        indices = np.random.choice(fmap_all_flat.shape[0], n_samples, replace=False)
        fmap_sampled = fmap_all_flat[indices]
        print(f"[DEBUG] Сэмплировано {n_samples} пикселей из {fmap_all_flat.shape[0]}")
    else:
        fmap_sampled = fmap_all_flat
        indices = np.arange(fmap_all_flat.shape[0])
    
    # Уменьшаем количество признаков с помощью PCA
    from sklearn.decomposition import PCA
    n_components = min(30, fmap_sampled.shape[1])  # Уменьшили до 30 компонент
    pca = PCA(n_components=n_components, random_state=42)
    fmap_reduced = pca.fit_transform(fmap_sampled)
    print(f"[DEBUG] Размер после PCA: {fmap_reduced.shape}")
    
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=3)  # Уменьшили n_init
    labels_sampled = kmeans.fit_predict(fmap_reduced)
    
    # Применяем кластеризацию ко всем пикселям
    if fmap_all_flat.shape[0] > n_samples:
        # Используем обученный KMeans для всех пикселей
        fmap_all_reduced = pca.transform(fmap_all_flat)
        labels = kmeans.predict(fmap_all_reduced)
    else:
        labels = labels_sampled
    
    # Применяем пространственную регуляризацию для улучшения связности
    from skimage.morphology import closing, opening, remove_small_objects
    from skimage.measure import label, regionprops
    from scipy.ndimage import gaussian_filter
    
    mask = labels.reshape(H, W)
    
    # Сглаживаем маску для уменьшения шума
    mask_smooth = gaussian_filter(mask.astype(float), sigma=0.5)
    mask_smooth = np.round(mask_smooth).astype(int)
    
    # Удаляем мелкие области
    mask_cleaned = remove_small_objects(mask_smooth, min_size=50)
    
    # Применяем морфологические операции для улучшения связности
    mask_cleaned = closing(mask_cleaned, np.ones((3, 3)))
    mask_cleaned = opening(mask_cleaned, np.ones((2, 2)))
    
    # Переиндексируем кластеры, чтобы они были последовательными
    unique_labels = np.unique(mask_cleaned)
    mask_final = np.zeros_like(mask_cleaned)
    for i, label_id in enumerate(unique_labels):
        mask_final[mask_cleaned == label_id] = i
    
    mask = mask_final
    
    print(f"[DEBUG] Размер маски: {mask.shape}")
    print(f"[DEBUG] Уникальные кластеры: {np.unique(mask)}")
    
    # Цвета
    colors = np.random.randint(0, 255, (n_clusters, 3), dtype=np.uint8)
    color_map = colors[mask]
    cluster_info = {i: {'color': colors[i].tolist()} for i in range(n_clusters)}
    masks_by_cluster = {i: (mask == i).astype(np.uint8) for i in range(n_clusters)}
    
    return mask, color_map, cluster_info, masks_by_cluster
