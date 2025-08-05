"""
tiling.py

Функции для разрезки больших снимков на плитки и подготовки расширенного стека каналов Sentinel-2 + индексов (NDVI, NDWI, NDBI).
"""
import numpy as np
import rasterio
from rasterio.windows import Window
from typing import List, Dict, Tuple
import os
from rasterio.transform import Affine

def prepare_multichannel_tile(tile_dict: dict) -> np.ndarray:
    """
    Собирает расширенный стек каналов и индексов для одной плитки.
    tile_dict: dict { 'B02': np.ndarray, ..., 'B12': np.ndarray }
    Возвращает: np.ndarray (C, H, W), где C = все доступные каналы + NDVI + NDWI + NDBI
    """
    channels = []
    channel_order = [
        'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B8A', 'B09', 'B11', 'B12'
    ]
    for ch in channel_order:
        if ch in tile_dict:
            channels.append(tile_dict[ch])
    
    # Проверка, есть ли хоть один канал
    if not channels:
        raise ValueError("Не найдено ни одного канала среди: " + str(channel_order))
    
    # Приводим к numpy массиву (C, H, W)
    arr = np.stack(channels, axis=0)
    
    # Индексы
    ndvi = None
    ndwi = None
    ndbi = None
    # NDVI: (B8A - B04) / (B8A + B04)
    if 'B8A' in tile_dict and 'B04' in tile_dict:
        ndvi = (tile_dict['B8A'] - tile_dict['B04']) / (tile_dict['B8A'] + tile_dict['B04'] + 1e-6)
        arr = np.concatenate([arr, ndvi[None, ...]], axis=0)
    # NDWI: (B03 - B8A) / (B03 + B8A)
    if 'B03' in tile_dict and 'B8A' in tile_dict:
        ndwi = (tile_dict['B03'] - tile_dict['B8A']) / (tile_dict['B03'] + tile_dict['B8A'] + 1e-6)
        arr = np.concatenate([arr, ndwi[None, ...]], axis=0)
    # NDBI: (B11 - B8A) / (B11 + B8A)
    if 'B11' in tile_dict and 'B8A' in tile_dict:
        ndbi = (tile_dict['B11'] - tile_dict['B8A']) / (tile_dict['B11'] + tile_dict['B8A'] + 1e-6)
        arr = np.concatenate([arr, ndbi[None, ...]], axis=0)
    
    # Убедимся, что у нас трехмерный массив (C, H, W), даже если C=1
    if len(arr.shape) == 2:
        # Превращаем 2D-массив (H, W) в 3D-массив (1, H, W)
        arr = arr[np.newaxis, ...]
    
    return arr

def split_geotiff_to_tiles(
    input_path: str,
    tile_size: int = 512,
    output_dir: str = "tiles",
    prefix: str = None
) -> list:
    """
    Разрезает GeoTIFF на плитки tile_size x tile_size с сохранением геореференции.
    Сохраняет плитки в output_dir, возвращает список путей к плиткам.
    
    :param input_path: Путь к исходному GeoTIFF
    :param tile_size: Размер плитки (по умолчанию 512)
    :param output_dir: Директория для сохранения плиток
    :param prefix: Префикс для имен файлов плиток (по умолчанию имя исходного файла)
    :return: Список путей к сохранённым плиткам
    """
    os.makedirs(output_dir, exist_ok=True)
    tile_paths = []
    with rasterio.open(input_path) as src:
        width = src.width
        height = src.height
        meta = src.meta.copy()
        if prefix is None:
            prefix = os.path.splitext(os.path.basename(input_path))[0]
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                w = min(tile_size, width - x)
                h = min(tile_size, height - y)
                window = Window(x, y, w, h)
                transform = src.window_transform(window)
                meta.update({
                    "height": h,
                    "width": w,
                    "transform": transform
                })
                tile_path = os.path.join(
                    output_dir,
                    f"{prefix}_x{x}_y{y}.tif"
                )
                with rasterio.open(tile_path, "w", **meta) as dst:
                    dst.write(src.read(window=window))
                tile_paths.append(tile_path)
    return tile_paths

def load_channels_from_files(
    folder: str,
    base_name: str,
    channels: list,
    tile_size: int = None,
    row: int = None,
    col: int = None,
    x0: int = None,
    y0: int = None,
    suffix: str = '_20m.tif'
) -> dict:
    """
    Загружает указанные каналы из отдельных файлов в папке.
    Если tile_size и (row, col) заданы — читает только нужный тайл по сетке.
    Если tile_size и (x0, y0) заданы — читает тайл по произвольным координатам.
    Если ничего не задано — читает весь канал.
    Возвращает: dict { 'B02': np.ndarray, ... }
    """
    tile_dict = {}
    for ch in channels:
        filename = f"{base_name}_{ch}{suffix}"
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            continue
        with rasterio.open(path) as src:
            if tile_size is not None:
                if x0 is not None and y0 is not None:
                    window = rasterio.windows.Window(x0, y0, tile_size, tile_size)
                    arr = src.read(1, window=window)
                elif row is not None and col is not None:
                    window = rasterio.windows.Window(col * tile_size, row * tile_size, tile_size, tile_size)
                    arr = src.read(1, window=window)
                else:
                    arr = src.read(1)
            else:
                arr = src.read(1)
            tile_dict[ch] = arr
    return tile_dict
