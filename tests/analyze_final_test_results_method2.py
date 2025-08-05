import os
import json
import glob
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.patches as mpatches
import itertools
from collections import defaultdict
import markdown
from pathlib import Path

# Добавляем путь к модулю
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Локальное определение функции get_worldcover_legend
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

RESULTS_ROOT = "tests/final_test/method_2"
REPORT_MD = os.path.join(RESULTS_ROOT, "final_report.md")

# Для генерации выводов через OpenAI
try:
    import openai
    OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_KEY:
        openai.api_key = OPENAI_KEY
    else:
        openai = None
except ImportError:
    openai = None

SEGMENTATION_METHODS = ["kmeans", "watershed_kmeans", "watershed_ndvi", "som", "unet"]
NOT_MODELS = SEGMENTATION_METHODS + ["ndvi", "kmeans", "gemini-2.5-flash-preview-04-17", "grok-4-0709"]

# Полный список моделей из тестового файла (исключили grok-4-0709 и gemini-2.5-flash-preview-04-17)
EXPECTED_MODELS = [
    "grok-2-vision-1212",
    "o4-mini",
    "gpt-4o-2024-08-06",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4o-mini-2024-07-18",
    "gemini-2.5-pro-preview-05-06",
    "claude-3-7-sonnet-20250219",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-haiku-20241022"
]

# --- Генерация legend.png для маски ---
def generate_legend_image(tile, method, model, legend_dict, out_path):
    # legend_dict: {class_code: (class_name, color)}
    fig, ax = plt.subplots(figsize=(max(4, len(legend_dict)), 1))
    patches = []
    for code, (name, color) in legend_dict.items():
        hex_color = '#%02x%02x%02x' % tuple(color)
        patches.append(mpatches.Patch(color=hex_color, label=f"{code}: {name}"))
    ax.legend(handles=patches, loc='center', ncol=len(legend_dict), frameon=False)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches='tight', pad_inches=0.1)
    plt.close()

# --- Исправленный сбор метрик ---
def collect_metrics():
    data = []
    print(f"[INFO] Анализируем результаты из: {RESULTS_ROOT}")
    
    tile_dirs = sorted(glob.glob(os.path.join(RESULTS_ROOT, "tile_*")))
    print(f"[INFO] Найдено {len(tile_dirs)} директорий tile")
    
    for tile_dir in tile_dirs:
        tile_idx = int(tile_dir.split("_")[-1])
        print(f"[INFO] Обрабатываем tile_{tile_idx}")
        
        metrics_files = glob.glob(os.path.join(tile_dir, "*_vlm_vs_worldcover_metrics.json"))
        print(f"[INFO] Найдено {len(metrics_files)} файлов метрик в tile_{tile_idx}")
        
        for metrics_file in metrics_files:
            filename = os.path.basename(metrics_file)
            print(f"[DEBUG] Обрабатываем файл: {filename}")
            
            # --- Корректно извлекаем method и model ---
            method = None
            model = None
            
            # Ищем метод сегментации
            if 'watershed_kmeans' in filename:
                method = 'watershed_kmeans'
            elif 'watershed_ndvi' in filename:
                method = 'watershed_ndvi'
            elif 'kmeans' in filename and 'watershed' not in filename:
                method = 'kmeans'
            elif 'som' in filename:
                method = 'som'
            elif 'unet' in filename:
                method = 'unet'
            
            # Ищем модель (после метода, до _vlm_vs_worldcover_metrics.json)
            if method:
                # Убираем метод из имени файла
                remaining = filename.replace(f"{method}_", "")
                # Убираем суффикс
                remaining = remaining.replace("_vlm_vs_worldcover_metrics.json", "")
                model = remaining.strip()  # Убираем лишние пробелы
                
                print(f"[DEBUG] Извлечено: method={method}, model={model}")
            
            # Только методы из справочника
            if method not in SEGMENTATION_METHODS:
                print(f"[DEBUG] Пропускаем: method={method} не в списке")
                continue
                
            try:
                with open(metrics_file, 'r', encoding='utf-8') as f:
                    metrics = json.load(f)
                
                # Извлекаем per_class данные из самого файла метрик
                per_class = metrics.get("per_class", {})
                
                # Если per_class пустой, но есть метрики по классам в отдельных полях
                if not per_class and any(key in metrics for key in ['iou', 'precision', 'recall', 'f1']):
                    per_class = {}
                    classes = metrics.get('classes', [])
                    for cls in classes:
                        cls_str = str(cls)
                        per_class[cls_str] = {
                            'iou': metrics.get('iou', {}).get(cls_str, 0.0),
                            'precision': metrics.get('precision', {}).get(cls_str, 0.0),
                            'recall': metrics.get('recall', {}).get(cls_str, 0.0),
                            'f1': metrics.get('f1', {}).get(cls_str, 0.0),
                            'pixel_accuracy': metrics.get('pixel_accuracy', 0.0),
                            'support_true': np.nan,  # Не доступно в текущем формате
                            'support_pred': np.nan   # Не доступно в текущем формате
                        }
                
                f1_val = np.nan
                if 'f1' in metrics and isinstance(metrics['f1'], dict) and len(metrics['f1']) > 0:
                    f1_val = np.mean(list(metrics['f1'].values()))
                
                data.append({
                    "tile": tile_idx,
                    "method": method,
                    "model": model,
                    "accuracy": metrics.get("pixel_accuracy", np.nan),
                    "iou": metrics.get("mean_iou", np.nan),
                    "f1": f1_val,
                    "kappa": metrics.get("kappa", np.nan),
                    "per_class": per_class
                })
                print(f"[DEBUG] Добавлена запись: tile={tile_idx}, method={method}, model={model}")
            except Exception as e:
                print(f"[ERROR] Ошибка при обработке файла {metrics_file}: {e}")
                continue
    
    print(f"[INFO] Собрано {len(data)} записей метрик")
    return pd.DataFrame(data)

# --- Исправляю построение графиков ---
def plot_metrics(df, metric, out_path):
    plt.figure(figsize=(10, 6))
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS]
    for model in true_models:
        model_df = df[df['model'] == model]
        present_methods = model_df['method'].unique()
        vals = model_df.groupby('method')[metric].mean().reindex(present_methods)
        plt.plot(present_methods, vals.values, marker='o', label=model)
    plt.title(f"Mean {metric} by Segmentation Methods")
    plt.xlabel("Segmentation Method")
    plt.ylabel(metric)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()

# --- Summary & Rankings section ---
def generate_summary_section(df, results_root):
    lines = ["# Summary & Rankings\n"]
    # Топ-3 метода сегментации
    present_methods = sorted(df['method'].unique())
    method_scores = df.groupby('method')[['accuracy', 'iou', 'f1']].mean().loc[present_methods].sort_values('iou', ascending=False)
    lines.append("## Top-3 Segmentation Methods (by mean IoU)\n")
    lines.append(method_scores.head(3).to_markdown())
    # Barplot
    plt.figure(figsize=(8,4))
    sns.barplot(x=method_scores.index, y=method_scores['iou'])
    plt.title('Mean IoU by Segmentation Method')
    plt.ylabel('Mean IoU')
    plt.xlabel('Segmentation Method')
    plt.tight_layout()
    barplot_path = os.path.join(results_root, "barplot_method_iou.png")
    plt.savefig(barplot_path)
    plt.close()
    lines.append(f"![]({os.path.basename(barplot_path)})\n")
    # Топ-5 моделей (исключаем grok-4-0709 и gemini-2.5-flash-preview-04-17)
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    present_models = sorted([m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models])
    model_scores = df[~df['model'].isin(NOT_MODELS + excluded_models)].groupby('model')[['accuracy', 'iou', 'f1']].mean().loc[present_models].sort_values('iou', ascending=False)
    lines.append("## Top-5 Models (by mean IoU)\n")
    lines.append(model_scores.head(5).to_markdown())
    plt.figure(figsize=(10,4))
    sns.barplot(x=model_scores.index, y=model_scores['iou'])
    plt.title('Mean IoU by Model')
    plt.ylabel('Mean IoU')
    plt.xlabel('Model')
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    barplot_model_path = os.path.join(results_root, "barplot_model_iou.png")
    plt.savefig(barplot_model_path)
    plt.close()
    lines.append(f"![]({os.path.basename(barplot_model_path)})\n")
    # Сравнение комбинаций (метод+модель) - исключаем указанные модели
    combo_scores = df[~df['model'].isin(NOT_MODELS + excluded_models)].groupby(['method','model'])[['accuracy','iou','f1']].mean().reset_index()
    combo_methods = sorted(combo_scores['method'].unique())
    combo_models = sorted(combo_scores['model'].unique())
    combo_pivot = combo_scores.pivot(index='method', columns='model', values='iou').loc[combo_methods, combo_models]
    lines.append("## Segmentation+Model Combination (mean IoU)\n")
    lines.append(combo_pivot.to_markdown())
    plt.figure(figsize=(max(8, len(combo_models)), max(4, len(combo_methods)//2)))
    sns.heatmap(combo_pivot, annot=True, fmt='.2f', cmap='viridis')
    plt.title('Mean IoU for Segmentation+Model Combinations')
    plt.ylabel('Segmentation Method')
    plt.xlabel('Model')
    plt.tight_layout()
    heatmap_combo_path = os.path.join(results_root, "heatmap_combo_iou.png")
    plt.savefig(heatmap_combo_path)
    plt.close()
    lines.append(f"![]({os.path.basename(heatmap_combo_path)})\n")
    # Per-class IoU heatmap (по основным классам)
    per_class_iou = {}
    for _, row in df.iterrows():
        method = row['method']
        model = row['model']
        if model in NOT_MODELS:
            continue
        for cls, m in row.get('per_class', {}).items():
            key = (method, model, cls)
            per_class_iou.setdefault(key, []).append(m.get('iou', np.nan))
    per_class_iou_mean = {}
    for (method, model, cls), vals in per_class_iou.items():
        per_class_iou_mean[(method, model, cls)] = np.nanmean(vals)
    all_methods = sorted({k[0] for k in per_class_iou_mean.keys()})
    all_models = sorted({k[1] for k in per_class_iou_mean.keys()})
    all_classes = sorted({cls for (_,_,cls) in per_class_iou_mean.keys()})
    
    # Получаем названия классов
    wc_legend = get_worldcover_legend()
    
    for cls in all_classes:
        data = np.full((len(all_methods), len(all_models)), np.nan)
        for i, method in enumerate(all_methods):
            for j, model in enumerate(all_models):
                data[i,j] = per_class_iou_mean.get((method, model, cls), np.nan)
        df_hm = pd.DataFrame(data, index=all_methods, columns=all_models)
        
        # Получаем название класса
        class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
        
        lines.append(f"### Per-class IoU for class {cls} | {class_name}\n")
        lines.append(df_hm.to_markdown())
        plt.figure(figsize=(max(8, len(all_models)), max(4, len(all_methods)//2)))
        sns.heatmap(df_hm, annot=True, fmt='.2f', cmap='magma')
        plt.title(f'Per-class IoU for class {cls} | {class_name}')
        plt.ylabel('Segmentation Method')
        plt.xlabel('Model')
        plt.tight_layout()
        heatmap_class_path = os.path.join(results_root, f"heatmap_iou_class_{cls}.png")
        plt.savefig(heatmap_class_path)
        plt.close()
        lines.append(f"![]({os.path.basename(heatmap_class_path)})\n")
    
    # WorldCover Class Analysis
    lines.append("\n## WorldCover Class Analysis\n")
    
    # Collect metrics by WorldCover classes
    wc_class_metrics = {}
    for _, row in df.iterrows():
        per_class = row.get('per_class', {})
        for cls, metrics in per_class.items():
            if cls not in wc_class_metrics:
                wc_class_metrics[cls] = {'iou': [], 'f1': [], 'precision': [], 'recall': []}
            wc_class_metrics[cls]['iou'].append(metrics.get('iou', np.nan))
            wc_class_metrics[cls]['f1'].append(metrics.get('f1', np.nan))
            wc_class_metrics[cls]['precision'].append(metrics.get('precision', np.nan))
            wc_class_metrics[cls]['recall'].append(metrics.get('recall', np.nan))
    
    # Create summary table
    lines.append("## Summary Table of Average Metrics\n")
    summary_data = []
    for cls in sorted(wc_class_metrics.keys(), key=lambda x: int(x) if str(x).isdigit() else x):
        class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
        metrics = wc_class_metrics[cls]
        summary_data.append({
            'Class Code': cls,
            'Class Name': class_name,
            'Mean IoU': np.nanmean(metrics['iou']),
            'Mean F1': np.nanmean(metrics['f1']),
            'Mean Precision': np.nanmean(metrics['precision']),
            'Mean Recall': np.nanmean(metrics['recall']),
            'Count': len(metrics['iou'])
        })
    
    if summary_data:
        summary_df = pd.DataFrame(summary_data)
        lines.append(summary_df.to_markdown(index=False))
    else:
        lines.append("No class data available.\n")
    
    # Aggregated metrics by classes
    lines.append("\n## Aggregated Per-Class Metrics\n")
    aggregated_lines = aggregate_per_class_metrics(df)
    lines.extend(aggregated_lines[1:])  # Skip header as it's already there
    
    # Brief analysis
    lines.append("\n## Brief Class Analysis\n")
    if summary_data:
        # Sort by IoU
        summary_sorted = sorted(summary_data, key=lambda x: x['Mean IoU'], reverse=True)
        
        lines.append("**Best classes by IoU:**\n")
        for item in summary_sorted[:5]:
            lines.append(f"- **Class {item['Class Code']} - {item['Class Name']}**: IoU={item['Mean IoU']:.4f}, F1={item['Mean F1']:.4f} ({item['Count']} measurements)")
        
        lines.append("\n**Worst classes by IoU:**\n")
        for item in summary_sorted[-5:]:
            lines.append(f"- **Class {item['Class Code']} - {item['Class Name']}**: IoU={item['Mean IoU']:.4f}, F1={item['Mean F1']:.4f} ({item['Count']} measurements)")
    else:
        lines.append("No data available for analysis.\n")
    
    return lines

# --- Генерация выводов через OpenAI ---
def generate_gpt_summary(df):
    """
    Генерирует анализ результатов с помощью GPT-4
    """
    try:
        # Импортируем функцию получения секретов из openai_adapter
        from new_pipeline.vlm_adapters.openai_adapter import get_secret, get_openai_client
        
        # Получаем API ключ
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            print("[WARN] OpenAI API ключ не найден. Пропускаем GPT анализ.")
            return None
        
        # Создаем клиент OpenAI
        client = get_openai_client()
        
        # Подготавливаем данные для анализа
        methods = SEGMENTATION_METHODS
        excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
        true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
        
        filtered_df = df[df['model'].isin(true_models) & df['method'].isin(methods)]
        
        # Создаем сводную таблицу
        pivot_table = filtered_df.pivot_table(
            index=['model', 'method'], 
            values=['accuracy', 'iou', 'f1', 'kappa'], 
            aggfunc='mean'
        )
        
        prompt = f"""
You have results from comparing various VLM models and segmentation methods using accuracy, IoU, and F1 metrics. Here's the summary table:

{pivot_table.to_markdown()}

Please provide a comprehensive analysis with the following structure:

## Key Findings
- **Best performing models and methods**
- **Performance patterns and trends**
- **Surprising results or anomalies**

## Model Performance Analysis
- **Top 3 models by IoU**
- **Top 3 models by accuracy**
- **Consistency across different methods**

## Method Performance Analysis
- **Best segmentation methods**
- **Method-specific strengths and weaknesses**
- **Method-model combinations**

## Recommendations
- **For production use**
- **For research purposes**
- **Areas for improvement**

Please provide detailed insights with specific numbers and clear recommendations.
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert data analyst specializing in computer vision and machine learning evaluation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"[ERROR] Ошибка при генерации GPT анализа: {e}")
        return None

# --- Вспомогательная функция для поиска legend.png ---
def find_legend_path(tile, method, model):
    # Пробуем несколько вариантов имени файла
    candidates = [
        f"tile_{tile}/{method}_legend_{model}.png",
        f"tile_{tile}/{method}_legend_{model.replace('-', '_')}.png",
        f"tile_{tile}/{method}_legend.png",
        f"tile_{tile}/legend_{model}.png",
        f"tile_{tile}/legend.png"
    ]
    
    # Также пробуем варианты с пробелами в именах моделей
    model_clean = model.replace(' ', '_').replace('-', '_')
    candidates.extend([
        f"tile_{tile}/{method}_legend_{model_clean}.png",
        f"tile_{tile}/legend_{model_clean}.png"
    ])
    
    for path in candidates:
        full_path = os.path.join(RESULTS_ROOT, path)
        if os.path.exists(full_path):
            return path
    return None

# --- Подробный markdown-отчёт ---
def generate_full_report(df, plots, summary_text, summary_section, missing_combinations=None):
    lines = []
    lines.extend(summary_section)
    # --- Section about missing combinations ---
    lines.append("\n---\n\n# Completeness Check\n")
    if missing_combinations is not None:
        if len(missing_combinations) == 0:
            lines.append("All tile-method-model combinations are present in the results.\n")
        else:
            lines.append("**Missing results for the following combinations (tile, method, model):**\n")
            lines.append("| Tile | Method | Model |")
            lines.append("|------|--------|-------|")
            for tile, method, model in missing_combinations:
                lines.append(f"| tile_{tile} | {method} | {model} |")
            lines.append("")
    lines.append("\n---\n\n# Final Test Report\n")
    tiles = sorted(df['tile'].unique())
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    lines.append("## Summary Table of Average Metrics\n")
    pivot = df[df['model'].isin(true_models) & df['method'].isin(methods)].pivot_table(index=['model', 'method'], values=['accuracy', 'iou', 'f1', 'kappa'], aggfunc='mean')
    lines.append(pivot.to_markdown())
    lines.append("\n## Visualizations\n")
    for metric, plot_path in plots.items():
        lines.append(f"### {metric}")
        lines.append(f"![]({os.path.basename(plot_path)})\n")
    if summary_text:
        lines.append("\n## Automated Insights (OpenAI GPT-4.1)\n")
        lines.append(summary_text)
    # Используем локальную функцию get_worldcover_legend
    wc_legend = get_worldcover_legend()
    for tile in tiles:
        lines.append(f"\n---\n\n## Tile {tile}")
        
        # Add TCI and worldcover_mask.png for each tile
        tci_path = f"tile_{tile}/tile_TCI_{tile}.png"
        wc_mask_path = f"tile_{tile}/worldcover_mask.png"
        lines.append("### Source Images")
        lines.append("| Type | Image |")
        lines.append("|------|-------|")
        lines.append(f"| TCI (RGB) | ![]({tci_path}) |")
        lines.append(f"| WorldCover Ground Truth | ![]({wc_mask_path}) |")
        lines.append("")
        
        tile_df = df[df['tile'] == tile]
        present_methods = sorted(tile_df['method'].unique())
        present_models = sorted([m for m in tile_df['model'].unique() if m not in NOT_MODELS])
        
        # Сначала показываем маски сегментации для каждого метода
        for method in present_methods:
            lines.append(f"\n### {method} — Segmentation Masks")
            # Ищем файлы масок сегментации
            segmentation_mask_path = f"tile_{tile}/{method}_mask_{tile}.png"
            segmentation_mask_abspath = os.path.join(RESULTS_ROOT, segmentation_mask_path)
            if os.path.exists(segmentation_mask_abspath):
                lines.append("| Type | Image |")
                lines.append("|------|-------|")
                lines.append(f"| Segmentation Mask | ![]({segmentation_mask_path}) |")
            else:
                lines.append("*Segmentation mask file not found*")
            lines.append("")
        
        # Теперь показываем VLM результаты для каждого метода и модели
        for method in present_methods:
            for model in present_models:
                row = tile_df[(tile_df['method'] == method) & (tile_df['model'] == model)]
                if row.empty:
                    continue
                row = row.iloc[0]
                lines.append(f"\n### {method} — {model}")
                lines.append("| Metric | Value |")
                lines.append("|--------|-------|")
                for m in ['accuracy', 'iou', 'f1', 'kappa']:
                    val = row.get(m, None)
                    sval = f"{val:.4f}" if isinstance(val, float) and not np.isnan(val) else "—"
                    lines.append(f"| {m} | {sval} |")
                mask_path = f"tile_{tile}/{method}_vlm2wc_{model}.png"
                json_path = f"tile_{tile}/{method}_mask_{model}_vlm_categories.json"
                lines.append(f"| Mask | ![]({mask_path}) |")
                legend_path = f"tile_{tile}/{method}_legend_{model}.png"
                legend_abspath = os.path.join(RESULTS_ROOT, legend_path)
                if not os.path.exists(legend_abspath):
                    generate_legend_image(tile, method, model, wc_legend, legend_abspath)
                lines.append(f"| Legend | ![]({legend_path}) |")
                lines.append(f"| JSON | [json]({json_path}) |")
                per_class = row.get('per_class', {})
                if per_class:
                    lines.append("\n#### Per-class metrics\n")
                    lines.append("| Class Code | Class Name (EN) | IoU | Precision | Recall | F1 | Pixel Acc | Support True | Support Pred |")
                    lines.append("|------------|----------------|-----|-----------|--------|----|-----------|-------------|-------------|")
                    for cls, m in per_class.items():
                        iou = m.get('iou', float('nan'))
                        prec = m.get('precision', float('nan'))
                        rec = m.get('recall', float('nan'))
                        f1 = m.get('f1', float('nan'))
                        pa = m.get('pixel_accuracy', float('nan'))
                        st = m.get('support_true', float('nan'))
                        sp = m.get('support_pred', float('nan'))
                        def fmt(x):
                            return f"{x:.4f}" if isinstance(x, float) and not np.isnan(x) else "—"
                        # Получаем английское название класса
                        class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
                        lines.append(f"| {cls} | {class_name} | {fmt(iou)} | {fmt(prec)} | {fmt(rec)} | {fmt(f1)} | {fmt(pa)} | {fmt(st)} | {fmt(sp)} |")
                else:
                    # Отладочная информация
                    if method == 'unet':
                        print(f"[DEBUG] U-Net {model}: per_class is empty or None")
                        print(f"[DEBUG] row keys: {list(row.keys())}")
                        print(f"[DEBUG] per_class value: {per_class}")
    # PROMPT для GPT-4.1
    lines.append("\n---\n\n## Findings & Insights (GPT-4.1)\n")
    
    # Генерируем реальный анализ вместо PROMPT
    try:
        detailed_analysis = generate_detailed_analysis(df, plots, summary_section)
        lines.append(detailed_analysis)
    except Exception as e:
        print(f"[WARN] OpenAI API недоступен, используем локальный анализ: {e}")
        local_analysis = generate_local_analysis(df, plots, summary_section)
        lines.append(local_analysis)
    
    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"[INFO] Итоговый отчёт сохранён: {REPORT_MD}")

def generate_full_report_english(df, plots, summary_text, summary_section, missing_combinations=None):
    """Английская версия отчета"""
    lines = []
    # Добавляем английские заголовки для summary_section
    english_summary = []
    for line in summary_section:
        if "Анализ по классам WorldCover" in line:
            english_summary.append("## WorldCover Class Analysis")
        elif "Сводная таблица" in line:
            english_summary.append("## Summary Table of Average Metrics")
        elif "Агрегированные метрики" in line:
            english_summary.append("## Aggregated Per-Class Metrics")
        elif "Краткий анализ" in line:
            english_summary.append("## Brief Class Analysis")
        else:
            english_summary.append(line)
    lines.extend(english_summary)
    
    # --- Секция о пропущенных комбинациях ---
    lines.append("\n---\n\n# Completeness Check\n")
    if missing_combinations is not None:
        if len(missing_combinations) == 0:
            lines.append("All tile-method-model combinations are present in the results.\n")
        else:
            lines.append("**Missing results for the following combinations (tile, method, model):**\n")
            lines.append("| Tile | Method | Model |")
            lines.append("|------|--------|-------|")
            for tile, method, model in missing_combinations:
                lines.append(f"| tile_{tile} | {method} | {model} |")
            lines.append("")
    lines.append("\n---\n\n# Final Test Report\n")
    tiles = sorted(df['tile'].unique())
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    lines.append("## Summary Table of Average Metrics\n")
    pivot = df[df['model'].isin(true_models) & df['method'].isin(methods)].pivot_table(index=['model', 'method'], values=['accuracy', 'iou', 'f1', 'kappa'], aggfunc='mean')
    lines.append(pivot.to_markdown())
    lines.append("\n## Visualizations\n")
    for metric, plot_path in plots.items():
        lines.append(f"### {metric}")
        lines.append(f"![]({os.path.basename(plot_path)})\n")
    if summary_text:
        lines.append("\n## Automated Insights (OpenAI GPT-4.1)\n")
        lines.append(summary_text)
    # Используем локальную функцию get_worldcover_legend
    wc_legend = get_worldcover_legend()
    for tile in tiles:
        lines.append(f"\n---\n\n## Tile {tile}")
        
        # Добавляем TCI и worldcover_mask.png для каждого tile
        tci_path = f"tile_{tile}/tile_TCI_{tile}.png"
        wc_mask_path = f"tile_{tile}/worldcover_mask.png"
        lines.append("### Source Images")
        lines.append("| Type | Image |")
        lines.append("|------|-------|")
        lines.append(f"| TCI (RGB) | ![]({tci_path}) |")
        lines.append(f"| WorldCover Ground Truth | ![]({wc_mask_path}) |")
        lines.append("")
        
        tile_df = df[df['tile'] == tile]
        present_methods = sorted(tile_df['method'].unique())
        present_models = sorted([m for m in tile_df['model'].unique() if m not in NOT_MODELS])
        
        # Сначала показываем маски сегментации для каждого метода
        for method in present_methods:
            lines.append(f"\n### {method} — Segmentation Masks")
            # Ищем файлы масок сегментации
            segmentation_mask_path = f"tile_{tile}/{method}_mask_{tile}.png"
            segmentation_mask_abspath = os.path.join(RESULTS_ROOT, segmentation_mask_path)
            if os.path.exists(segmentation_mask_abspath):
                lines.append("| Type | Image |")
                lines.append("|------|-------|")
                lines.append(f"| Segmentation Mask | ![]({segmentation_mask_path}) |")
            else:
                lines.append("*Segmentation mask file not found*")
            lines.append("")
        
        # Теперь показываем VLM результаты для каждого метода и модели
        for method in present_methods:
            for model in present_models:
                row = tile_df[(tile_df['method'] == method) & (tile_df['model'] == model)]
                if row.empty:
                    continue
                row = row.iloc[0]
                lines.append(f"\n### {method} — {model}")
                lines.append("| Metric | Value |")
                lines.append("|--------|-------|")
                for m in ['accuracy', 'iou', 'f1', 'kappa']:
                    val = row.get(m, None)
                    sval = f"{val:.4f}" if isinstance(val, float) and not np.isnan(val) else "—"
                    lines.append(f"| {m} | {sval} |")
                mask_path = f"tile_{tile}/{method}_vlm2wc_{model}.png"
                json_path = f"tile_{tile}/{method}_mask_{model}_vlm_categories.json"
                lines.append(f"| Mask | ![]({mask_path}) |")
                legend_path = f"tile_{tile}/{method}_legend_{model}.png"
                legend_abspath = os.path.join(RESULTS_ROOT, legend_path)
                if not os.path.exists(legend_abspath):
                    generate_legend_image(tile, method, model, wc_legend, legend_abspath)
                lines.append(f"| Legend | ![]({legend_path}) |")
                lines.append(f"| JSON | [json]({json_path}) |")
                per_class = row.get('per_class', {})
                if per_class:
                    lines.append("\n#### Per-class metrics\n")
                    lines.append("| Class Code | Class Name (EN) | IoU | Precision | Recall | F1 | Pixel Acc | Support True | Support Pred |")
                    lines.append("|------------|----------------|-----|-----------|--------|----|-----------|-------------|-------------|")
                    for cls, m in per_class.items():
                        iou = m.get('iou', float('nan'))
                        prec = m.get('precision', float('nan'))
                        rec = m.get('recall', float('nan'))
                        f1 = m.get('f1', float('nan'))
                        pa = m.get('pixel_accuracy', float('nan'))
                        st = m.get('support_true', float('nan'))
                        sp = m.get('support_pred', float('nan'))
                        def fmt(x):
                            return f"{x:.4f}" if isinstance(x, float) and not np.isnan(x) else "—"
                        # Получаем английское название класса
                        class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
                        lines.append(f"| {cls} | {class_name} | {fmt(iou)} | {fmt(prec)} | {fmt(rec)} | {fmt(f1)} | {fmt(pa)} | {fmt(st)} | {fmt(sp)} |")
                else:
                    # Отладочная информация
                    if method == 'unet':
                        print(f"[DEBUG] U-Net {model}: per_class is empty or None")
                        print(f"[DEBUG] row keys: {list(row.keys())}")
                        print(f"[DEBUG] per_class value: {per_class}")
    
    # Генерируем анализ на английском языке
    lines.append("\n---\n\n## Findings & Insights (GPT-4.1)\n")
    try:
        # Создаем английскую версию анализа
        english_analysis = generate_detailed_analysis_english(df, plots, summary_section)
        lines.append(english_analysis)
    except Exception as e:
        print(f"[WARN] OpenAI API недоступен, используем локальный анализ: {e}")
        local_analysis = generate_local_analysis_english(df, plots, summary_section)
        lines.append(local_analysis)
    
    # Генерируем локальный анализ
    try:
        local_analysis = generate_local_analysis_english(df, plots, summary_section)
        lines.extend(local_analysis.split('\n'))
        print("[INFO] Локальный анализ сгенерирован")
    except Exception as e:
        print(f"[ERROR] Ошибка при генерации локального анализа: {e}")
        lines.append("## Local Analysis of Results\n")
        lines.append("Error generating local analysis.\n")
    
    # Генерируем статистический анализ
    try:
        statistical_analysis = generate_statistical_analysis(df)
        lines.extend(statistical_analysis.split('\n'))
        print("[INFO] Статистический анализ сгенерирован")
    except Exception as e:
        print(f"[ERROR] Ошибка при генерации статистического анализа: {e}")
        lines.append("## Statistical Analysis\n")
        lines.append("Error generating statistical analysis.\n")
    
    # Сохраняем английскую версию
    report_en_md = os.path.join(RESULTS_ROOT, "final_report_en.md")
    with open(report_en_md, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"[INFO] English report saved: {report_en_md}")

def generate_detailed_analysis(df, plots, summary_section):
    """
    Генерирует подробный анализ результатов с помощью GPT-4.1
    """
    if openai is None:
        print("[WARN] OpenAI API недоступен, используем локальный анализ")
        return generate_local_analysis(df, plots, summary_section)
    
    # Подготавливаем данные для анализа
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    
    # Создаем сводную таблицу
    pivot_table = df[df['model'].isin(true_models) & df['method'].isin(methods)].pivot_table(
        index=['model', 'method'], 
        values=['accuracy', 'iou', 'f1', 'kappa'], 
        aggfunc='mean'
    )
    
    # Анализируем лучшие и худшие результаты
    best_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].max()
    worst_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].min()
    best_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].max()
    worst_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].min()
    
    # Находим лучшие комбинации
    best_accuracy_row = df[df['accuracy'] == best_accuracy].iloc[0] if not df.empty else None
    best_iou_row = df[df['iou'] == best_iou].iloc[0] if not df.empty else None
    
    # Анализ по классам
    # Используем локальную функцию get_worldcover_legend
    wc_legend = get_worldcover_legend()
    
    # Собираем данные по классам
    class_analysis = {}
    for _, row in df.iterrows():
        per_class = row.get('per_class', {})
        for cls, m in per_class.items():
            if cls not in class_analysis:
                class_analysis[cls] = {'iou': [], 'f1': [], 'count': 0}
            class_analysis[cls]['iou'].append(m.get('iou', 0))
            class_analysis[cls]['f1'].append(m.get('f1', 0))
            class_analysis[cls]['count'] += 1
    
    # Находим лучшие и худшие классы
    best_classes = []
    worst_classes = []
    if class_analysis:
        class_avg = {}
        for cls, data in class_analysis.items():
            if data['count'] > 0:
                avg_iou = np.mean(data['iou'])
                avg_f1 = np.mean(data['f1'])
                class_avg[cls] = (avg_iou, avg_f1)
        
        sorted_classes = sorted(class_avg.items(), key=lambda x: (-x[1][0], -x[1][1]))
        best_classes = sorted_classes[:3]
        worst_classes = sorted_classes[-3:]
    
    prompt = f"""
Ты эксперт по анализу результатов машинного обучения и компьютерного зрения. Проанализируй результаты тестирования различных методов сегментации и VLM моделей.

**Данные для анализа:**

1. **Сводная таблица результатов:**
{pivot_table.to_markdown()}

2. **Лучшие результаты:**
- Лучшая точность (accuracy): {best_accuracy:.4f}
- Лучший IoU: {best_iou:.4f}
- Лучшая комбинация по accuracy: {best_accuracy_row['method'] + ' + ' + best_accuracy_row['model'] if best_accuracy_row is not None else 'N/A'}
- Лучшая комбинация по IoU: {best_iou_row['method'] + ' + ' + best_iou_row['model'] if best_iou_row is not None else 'N/A'}

3. **Худшие результаты:**
- Худшая точность: {worst_accuracy:.4f}
- Худший IoU: {worst_iou:.4f}

4. **Анализ по классам WorldCover:**
"""
    
    if best_classes:
        prompt += "\n**Best classes by IoU/F1:**\n"
        for cls, (iou, f1) in best_classes:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            prompt += f"- Class {cls} - {class_name}: IoU={iou:.3f}, F1={f1:.3f}\n"
    
    if worst_classes:
        prompt += "\n**Worst classes by IoU/F1:**\n"
        for cls, (iou, f1) in worst_classes:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            prompt += f"- Class {cls} - {class_name}: IoU={iou:.3f}, F1={f1:.3f}\n"
    
    prompt += f"""

**Задача:** На основе этих данных сформулируй подробные выводы и рекомендации. Проанализируй:

1. **Общие результаты:**
   - Какие методы и модели показали лучшие результаты?
   - Есть ли явные лидеры или результаты близки?
   - Какие закономерности наблюдаются?

2. **Анализ по классам:**
   - Почему одни классы определяются лучше других?
   - Какие особенности классов влияют на точность?
   - Есть ли классы, которые особенно сложны для всех методов?

3. **Практические рекомендации:**
   - Какой метод/модель стоит использовать в продакшене?
   - Что можно улучшить?
   - Какие дополнительные тесты стоит провести?

4. **Интересные наблюдения:**
   - Что удивило в результатах?
   - Есть ли неожиданные паттерны?
   - Какие выводы можно сделать о качестве данных?

Пиши структурированно, с маркированными списками, на русском языке. Будь конкретным и давай практические рекомендации.
"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу результатов машинного обучения и компьютерного зрения. Твоя задача - дать глубокий, практический анализ результатов тестирования."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        return response.choices[0].message['content']
    except Exception as e:
        print(f"[WARN] Не удалось получить анализ от OpenAI: {e}")
        print("[WARN] Используем локальный анализ")
        return generate_local_analysis(df, plots, summary_section)

def generate_detailed_analysis_english(df, plots, summary_section):
    """
    Генерирует подробный анализ результатов на английском языке с помощью GPT-4.1
    """
    try:
        # Импортируем функцию получения секретов из openai_adapter
        from new_pipeline.vlm_adapters.openai_adapter import get_secret, get_openai_client
        
        # Получаем API ключ
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            print("[WARN] OpenAI API ключ не найден, используем локальный анализ")
            return generate_local_analysis_english(df, plots, summary_section)
        
        # Создаем клиент OpenAI
        client = get_openai_client()
    except Exception as e:
        print(f"[WARN] OpenAI API недоступен, используем локальный анализ: {e}")
        return generate_local_analysis_english(df, plots, summary_section)
    
    # Подготавливаем данные для анализа
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    
    # Создаем сводную таблицу
    pivot_table = df[df['model'].isin(true_models) & df['method'].isin(methods)].pivot_table(
        index=['model', 'method'], 
        values=['accuracy', 'iou', 'f1', 'kappa'], 
        aggfunc='mean'
    )
    
    # Анализируем лучшие и худшие результаты
    best_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].max()
    worst_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].min()
    best_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].max()
    worst_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].min()
    
    # Находим лучшие комбинации
    best_accuracy_row = df[df['accuracy'] == best_accuracy].iloc[0] if not df.empty else None
    best_iou_row = df[df['iou'] == best_iou].iloc[0] if not df.empty else None
    
    # Анализ по классам
    # Используем локальную функцию get_worldcover_legend
    wc_legend = get_worldcover_legend()
    
    # Собираем данные по классам
    class_analysis = {}
    for _, row in df.iterrows():
        per_class = row.get('per_class', {})
        for cls, m in per_class.items():
            if cls not in class_analysis:
                class_analysis[cls] = {'iou': [], 'f1': [], 'count': 0}
            class_analysis[cls]['iou'].append(m.get('iou', 0))
            class_analysis[cls]['f1'].append(m.get('f1', 0))
            class_analysis[cls]['count'] += 1
    
    # Находим лучшие и худшие классы
    best_classes = []
    worst_classes = []
    if class_analysis:
        class_avg = {}
        for cls, data in class_analysis.items():
            if data['count'] > 0:
                avg_iou = np.mean(data['iou'])
                avg_f1 = np.mean(data['f1'])
                class_avg[cls] = (avg_iou, avg_f1)
        
        sorted_classes = sorted(class_avg.items(), key=lambda x: (-x[1][0], -x[1][1]))
        best_classes = sorted_classes[:3]
        worst_classes = sorted_classes[-3:]
    
    prompt = f"""
You are an expert in machine learning and computer vision analysis. Analyze the results of testing various segmentation methods and VLM models.

**Data for analysis:**

1. **Summary table of results:**
{pivot_table.to_markdown()}

2. **Best results:**
- Best accuracy: {best_accuracy:.4f}
- Best IoU: {best_iou:.4f}
- Best combination by accuracy: {best_accuracy_row['method'] + ' + ' + best_accuracy_row['model'] if best_accuracy_row is not None else 'N/A'}
- Best combination by IoU: {best_iou_row['method'] + ' + ' + best_iou_row['model'] if best_iou_row is not None else 'N/A'}

3. **Worst results:**
- Worst accuracy: {worst_accuracy:.4f}
- Worst IoU: {worst_iou:.4f}

4. **WorldCover class analysis:**
"""
    
    if best_classes:
        prompt += "\n**Best classes by IoU/F1:**\n"
        for cls, (iou, f1) in best_classes:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            prompt += f"- Class {cls} ({class_name}): IoU={iou:.3f}, F1={f1:.3f}\n"
    
    if worst_classes:
        prompt += "\n**Worst classes by IoU/F1:**\n"
        for cls, (iou, f1) in worst_classes:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            prompt += f"- Class {cls} ({class_name}): IoU={iou:.3f}, F1={f1:.3f}\n"
    
    prompt += f"""

**Task:** Based on this data, formulate detailed conclusions and recommendations. Analyze:

1. **Overall results:**
   - Which methods and models showed the best results?
   - Are there clear leaders or are results close?
   - What patterns are observed?

2. **Class analysis:**
   - Why are some classes determined better than others?
   - What class features affect accuracy?
   - Are there classes that are particularly difficult for all methods?

3. **Practical recommendations:**
   - Which method/model should be used in production?
   - What can be improved?
   - What additional tests should be conducted?

4. **Interesting observations:**
   - What surprised you in the results?
   - Are there unexpected patterns?
   - What conclusions can be drawn about data quality?

Write structured, with bullet points, in English. Be specific and give practical recommendations.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert in machine learning and computer vision analysis. Your task is to provide deep, practical analysis of test results."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[WARN] Failed to get analysis from OpenAI: {e}")
        print("[WARN] Используем локальный анализ")
        return generate_local_analysis_english(df, plots, summary_section)

def generate_local_analysis(df, plots, summary_section):
    """
    Генерирует локальный анализ результатов без использования OpenAI API
    """
    # Подготавливаем данные для анализа
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    
    # Создаем сводную таблицу
    pivot_table = df[df['model'].isin(true_models) & df['method'].isin(methods)].pivot_table(
        index=['model', 'method'], 
        values=['accuracy', 'iou', 'f1', 'kappa'], 
        aggfunc='mean'
    )
    
    # Анализируем лучшие и худшие результаты
    best_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].max()
    worst_accuracy = df[df['model'].isin(true_models) & df['method'].isin(methods)]['accuracy'].min()
    best_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].max()
    worst_iou = df[df['model'].isin(true_models) & df['method'].isin(methods)]['iou'].min()
    
    # Находим лучшие комбинации
    best_accuracy_row = df[df['accuracy'] == best_accuracy].iloc[0] if not df.empty else None
    best_iou_row = df[df['iou'] == best_iou].iloc[0] if not df.empty else None
    
    # Анализ по классам
    # Используем локальную функцию get_worldcover_legend
    wc_legend = get_worldcover_legend()
    
    # Собираем данные по классам
    class_analysis = {}
    for _, row in df.iterrows():
        per_class = row.get('per_class', {})
        for cls, m in per_class.items():
            if cls not in class_analysis:
                class_analysis[cls] = {'iou': [], 'f1': [], 'count': 0}
            class_analysis[cls]['iou'].append(m.get('iou', 0))
            class_analysis[cls]['f1'].append(m.get('f1', 0))
            class_analysis[cls]['count'] += 1
    
    # Находим лучшие и худшие классы
    best_classes = []
    worst_classes = []
    if class_analysis:
        class_avg = {}
        for cls, data in class_analysis.items():
            if data['count'] > 0:
                avg_iou = np.mean(data['iou'])
                avg_f1 = np.mean(data['f1'])
                class_avg[cls] = (avg_iou, avg_f1)
        
        sorted_classes = sorted(class_avg.items(), key=lambda x: (-x[1][0], -x[1][1]))
        best_classes = sorted_classes[:3]
        worst_classes = sorted_classes[-3:]
    
    # Генерируем локальный анализ
    analysis = []
    analysis.append("## Local Analysis of Results\n")
    
    # Общие результаты
    analysis.append("### Overall Results\n")
    analysis.append(f"- **Best accuracy:** {best_accuracy:.4f}")
    analysis.append(f"- **Best IoU:** {best_iou:.4f}")
    analysis.append(f"- **Worst accuracy:** {worst_accuracy:.4f}")
    analysis.append(f"- **Worst IoU:** {worst_iou:.4f}")
    
    if best_accuracy_row is not None:
        analysis.append(f"- **Best combination by accuracy:** {best_accuracy_row['method']} + {best_accuracy_row['model']}")
    if best_iou_row is not None:
        analysis.append(f"- **Best combination by IoU:** {best_iou_row['method']} + {best_iou_row['model']}")
    
    # Анализ по методам
    analysis.append("\n### Analysis by Methods\n")
    method_stats = df[df['model'].isin(true_models) & df['method'].isin(methods)].groupby('method').agg({
        'accuracy': ['mean', 'std'],
        'iou': ['mean', 'std'],
        'f1': ['mean', 'std']
    }).round(4)
    
    for method in methods:
        if method in method_stats.index:
            acc_mean = method_stats.loc[method, ('accuracy', 'mean')]
            acc_std = method_stats.loc[method, ('accuracy', 'std')]
            iou_mean = method_stats.loc[method, ('iou', 'mean')]
            iou_std = method_stats.loc[method, ('iou', 'std')]
            f1_mean = method_stats.loc[method, ('f1', 'mean')]
            f1_std = method_stats.loc[method, ('f1', 'std')]
            analysis.append(f"- **{method}:** Accuracy={acc_mean:.4f}±{acc_std:.4f}, IoU={iou_mean:.4f}±{iou_std:.4f}, F1={f1_mean:.4f}±{f1_std:.4f}")
    
    # Анализ по моделям
    analysis.append("\n### Analysis by Models\n")
    model_stats = df[df['model'].isin(true_models) & df['method'].isin(methods)].groupby('model').agg({
        'accuracy': ['mean', 'std'],
        'iou': ['mean', 'std'],
        'f1': ['mean', 'std']
    }).round(4)
    
    # Сортируем модели по среднему IoU
    model_ranking = model_stats[('iou', 'mean')].sort_values(ascending=False)
    analysis.append("**Top-5 models by IoU:**")
    for i, (model, iou) in enumerate(model_ranking.head().items(), 1):
        analysis.append(f"{i}. {model}: IoU={iou:.4f}")
    
    # Анализ по классам
    if best_classes or worst_classes:
        analysis.append("\n### WorldCover Class Analysis\n")
        
        if best_classes:
            analysis.append("**Best classes by IoU/F1:**")
            for cls, (iou, f1) in best_classes:
                class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
                analysis.append(f"- Class {cls} - {class_name}: IoU={iou:.3f}, F1={f1:.3f}")
        
        if worst_classes:
            analysis.append("\n**Worst classes by IoU/F1:**")
            for cls, (iou, f1) in worst_classes:
                class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
                analysis.append(f"- Class {cls} - {class_name}: IoU={iou:.3f}, F1={f1:.3f}")
    
    # Practical recommendations
    analysis.append("\n### Practical Recommendations\n")
    analysis.append("- **For production:** Recommended to use combination with best IoU scores")
    analysis.append("- **For further analysis:** Additional tests on other datasets should be conducted")
    analysis.append("- **For improvement:** Try ensemble methods or fine-tuning models")
    
    return "\n".join(analysis)

def generate_local_analysis_english(df, plots, summary_section):
    """
    Генерирует локальный анализ результатов на английском языке без использования OpenAI API
    """
    try:
        # Подготавливаем данные для анализа
        methods = SEGMENTATION_METHODS
        excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
        true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
        
        # Фильтруем данные
        filtered_df = df[df['model'].isin(true_models) & df['method'].isin(methods)]
        
        if filtered_df.empty:
            return "## Local Analysis of Results\n\n**No valid data available for analysis.**\n"
        
        # Анализируем лучшие и худшие результаты
        best_accuracy = filtered_df['accuracy'].max()
        worst_accuracy = filtered_df['accuracy'].min()
        best_iou = filtered_df['iou'].max()
        worst_iou = filtered_df['iou'].min()
        
        # Находим лучшие комбинации
        best_accuracy_row = filtered_df.loc[filtered_df['accuracy'].idxmax()]
        best_iou_row = filtered_df.loc[filtered_df['iou'].idxmax()]
        
        # Анализ по методам
        method_stats = filtered_df.groupby('method').agg({
            'accuracy': ['mean', 'std'],
            'iou': ['mean', 'std'],
            'f1': ['mean', 'std']
        }).round(4)
        
        # Анализ по моделям
        model_stats = filtered_df.groupby('model').agg({
            'accuracy': ['mean', 'std'],
            'iou': ['mean', 'std'],
            'f1': ['mean', 'std']
        }).round(4)
        
        # Сортируем модели по среднему IoU
        model_ranking = model_stats[('iou', 'mean')].sort_values(ascending=False)
        
        # Генерируем анализ
        analysis = []
        analysis.append("## Local Analysis of Results\n")
        
        # Общие результаты
        analysis.append("### Overall Results\n")
        analysis.append(f"- **Best accuracy:** {best_accuracy:.4f}")
        analysis.append(f"- **Best IoU:** {best_iou:.4f}")
        analysis.append(f"- **Worst accuracy:** {worst_accuracy:.4f}")
        analysis.append(f"- **Worst IoU:** {worst_iou:.4f}")
        analysis.append(f"- **Best combination by accuracy:** {best_accuracy_row['method']} + {best_accuracy_row['model']}")
        analysis.append(f"- **Best combination by IoU:** {best_iou_row['method']} + {best_iou_row['model']}")
        
        # Анализ по методам
        analysis.append("\n### Analysis by Methods\n")
        for method in methods:
            if method in method_stats.index:
                acc_mean = method_stats.loc[method, ('accuracy', 'mean')]
                acc_std = method_stats.loc[method, ('accuracy', 'std')]
                iou_mean = method_stats.loc[method, ('iou', 'mean')]
                iou_std = method_stats.loc[method, ('iou', 'std')]
                f1_mean = method_stats.loc[method, ('f1', 'mean')]
                f1_std = method_stats.loc[method, ('f1', 'std')]
                analysis.append(f"- **{method}:** Accuracy={acc_mean:.4f}±{acc_std:.4f}, IoU={iou_mean:.4f}±{iou_std:.4f}, F1={f1_mean:.4f}±{f1_std:.4f}")
        
        # Анализ по моделям
        analysis.append("\n### Analysis by Models\n")
        analysis.append("**Top-5 models by IoU:**")
        for i, (model, iou) in enumerate(model_ranking.head().items(), 1):
            analysis.append(f"{i}. {model}: IoU={iou:.4f}")
        
        # Практические рекомендации
        analysis.append("\n### Practical Recommendations\n")
        best_method = method_stats[('iou', 'mean')].idxmax()
        best_model = model_stats[('iou', 'mean')].idxmax()
        
        analysis.append(f"- **For production:** Use {best_method} method with {best_model} model for best IoU performance")
        analysis.append("- **For further analysis:** Test on additional datasets to validate performance")
        analysis.append("- **For improvement:** Try ensemble methods combining top 3 models")
        
        return "\n".join(analysis)
        
    except Exception as e:
        print(f"[ERROR] Error in generate_local_analysis_english: {e}")
        return "## Local Analysis of Results\n\n**Error generating local analysis.**\n"

def check_completeness(df):
    """
    Проверяет, для каких комбинаций (tile, method, model) нет результатов.
    Выводит список пропусков в консоль и возвращает его для добавления в отчет.
    """
    all_tiles = sorted(df['tile'].unique())
    all_methods = SEGMENTATION_METHODS  # Используем все методы из справочника
    all_models = EXPECTED_MODELS  # Используем ожидаемые модели
    
    print(f"[INFO] Проверяем полноту результатов:")
    print(f"  - Тайлы: {all_tiles}")
    print(f"  - Методы: {all_methods}")
    print(f"  - Ожидаемые модели: {len(all_models)}")
    print(f"  - Найденные модели в данных: {sorted(df['model'].unique())}")
    
    missing = []
    total_expected = len(all_tiles) * len(all_methods) * len(all_models)
    total_found = 0
    
    for tile in all_tiles:
        for method in all_methods:
            for model in all_models:
                mask = (
                    (df['tile'] == tile) &
                    (df['method'] == method) &
                    (df['model'] == model)
                )
                if not mask.any():
                    missing.append((tile, method, model))
                else:
                    total_found += 1
    
    print(f"[INFO] Найдено результатов: {total_found}/{total_expected} ({total_found/total_expected*100:.1f}%)")
    
    if missing:
        print(f"[!] Отсутствуют результаты для {len(missing)} комбинаций (tile, method, model):")
        for tile, method, model in missing:
            print(f"  tile_{tile}: {method} + {model}")
    else:
        print("[OK] Все комбинации tile-method-model присутствуют в результатах.")
    return missing

def aggregate_per_class_metrics(df):
    """
    Агрегирует per-class метрики по всем тайлам, методам и моделям для реально встречавшихся классов.
    Возвращает markdown-таблицу и краткий анализ.
    """
    # Используем локальную функцию get_worldcover_legend вместо импорта
    wc_legend = get_worldcover_legend()
    
    # Собираем все значения по классам
    metrics_by_class = defaultdict(lambda: defaultdict(list))
    for _, row in df.iterrows():
        per_class = row.get('per_class', {})
        for cls, m in per_class.items():
            for metric in ['iou', 'precision', 'recall', 'f1', 'pixel_accuracy', 'support_true', 'support_pred']:
                val = m.get(metric, np.nan)
                metrics_by_class[cls][metric].append(val)
    
    # Проверяем, есть ли данные
    if not metrics_by_class:
        lines = ["# Aggregated Per-Class Metrics (all tiles, methods, models)\n"]
        lines.append("**No class data available for analysis.**\n")
        lines.append("Possible reasons:\n")
        lines.append("- per_class_metrics.json files are missing\n")
        lines.append("- Class metrics were not calculated\n")
        lines.append("- Data has different structure\n")
        return lines
    
    # Формируем таблицу
    lines = ["# Aggregated Per-Class Metrics (all tiles, methods, models)\n"]
    lines.append("| Class Code | Class Name (EN) | Mean IoU | Std IoU | Mean Prec | Std Prec | Mean Rec | Std Rec | Mean F1 | Std F1 | Mean PixAcc | Std PixAcc | Mean Supp True | Mean Supp Pred |")
    lines.append("|------------|----------------|----------|---------|----------|---------|---------|--------|--------|--------|-------------|-------------|---------------|---------------|")
    summary = []
    for cls in sorted(metrics_by_class.keys(), key=lambda x: int(x) if str(x).isdigit() else x):
        vals = metrics_by_class[cls]
        mean_iou = np.nanmean(vals['iou'])
        std_iou = np.nanstd(vals['iou'])
        mean_prec = np.nanmean(vals['precision'])
        std_prec = np.nanstd(vals['precision'])
        mean_rec = np.nanmean(vals['recall'])
        std_rec = np.nanstd(vals['recall'])
        mean_f1 = np.nanmean(vals['f1'])
        std_f1 = np.nanstd(vals['f1'])
        mean_pixacc = np.nanmean(vals['pixel_accuracy'])
        std_pixacc = np.nanstd(vals['pixel_accuracy'])
        mean_supp_true = np.nanmean(vals['support_true'])
        mean_supp_pred = np.nanmean(vals['support_pred'])
        
        # Получаем английское название класса
        class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
        
        lines.append(f"| {cls} | {class_name} | {mean_iou:.4f} | {std_iou:.4f} | {mean_prec:.4f} | {std_prec:.4f} | {mean_rec:.4f} | {std_rec:.4f} | {mean_f1:.4f} | {std_f1:.4f} | {mean_pixacc:.4f} | {std_pixacc:.4f} | {mean_supp_true:.1f} | {mean_supp_pred:.1f} |")
        summary.append((cls, mean_iou, mean_f1, len(vals['iou'])))
    
    # Краткий анализ
    lines.append("\n## Brief Class Analysis\n")
    if summary:
        summary_sorted = sorted(summary, key=lambda x: (-x[1], -x[2]))
        best = summary_sorted[:5]
        worst = summary_sorted[-5:]
        lines.append("**Best classes by IoU:**\n")
        for cls, iou, f1, count in best:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            lines.append(f"- **Class {cls} - {class_name}**: IoU={iou:.4f}, F1={f1:.4f} ({count} measurements)")
        lines.append("\n**Worst classes by IoU:**\n")
        for cls, iou, f1, count in worst:
            class_name = wc_legend.get(int(cls), ("Unknown", (0, 0, 0)))[0] if str(cls).isdigit() else "Unknown"
            lines.append(f"- **Class {cls} - {class_name}**: IoU={iou:.4f}, F1={f1:.4f} ({count} measurements)")
    else:
        lines.append("No data available for analysis.\n")
    
    return lines

def generate_statistical_analysis(df):
    """
    Генерирует статистический анализ результатов
    """
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    
    filtered_df = df[df['model'].isin(true_models) & df['method'].isin(methods)]
    
    analysis = []
    analysis.append("## Statistical Analysis\n")
    
    # Основные статистики
    analysis.append("### Summary Statistics\n")
    analysis.append(f"- **Total experiments:** {len(filtered_df)}")
    analysis.append(f"- **Unique models:** {len(filtered_df['model'].unique())}")
    analysis.append(f"- **Unique methods:** {len(filtered_df['method'].unique())}")
    analysis.append(f"- **Unique tiles:** {len(filtered_df['tile'].unique())}")
    
    # Статистики по метрикам
    for metric in ['accuracy', 'iou', 'f1']:
        values = filtered_df[metric]
        analysis.append(f"\n**{metric.upper()} Statistics:**")
        analysis.append(f"- Mean: {values.mean():.4f}")
        analysis.append(f"- Median: {values.median():.4f}")
        analysis.append(f"- Std: {values.std():.4f}")
        analysis.append(f"- Min: {values.min():.4f}")
        analysis.append(f"- Max: {values.max():.4f}")
        analysis.append(f"- Q1: {values.quantile(0.25):.4f}")
        analysis.append(f"- Q3: {values.quantile(0.75):.4f}")
    
    # Корреляционный анализ
    analysis.append("\n### Correlation Analysis\n")
    corr_matrix = filtered_df[['accuracy', 'iou', 'f1']].corr()
    analysis.append("**Correlation Matrix:**")
    analysis.append("| Metric | Accuracy | IoU | F1 |")
    analysis.append("|--------|----------|-----|----|")
    for i, metric in enumerate(['accuracy', 'iou', 'f1']):
        row = [metric]
        for j, metric2 in enumerate(['accuracy', 'iou', 'f1']):
            row.append(f"{corr_matrix.loc[metric, metric2]:.3f}")
        analysis.append(f"| {' | '.join(row)} |")
    
    # Анализ выбросов
    analysis.append("\n### Outlier Analysis\n")
    for metric in ['accuracy', 'iou', 'f1']:
        values = filtered_df[metric]
        Q1 = values.quantile(0.25)
        Q3 = values.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = values[(values < lower_bound) | (values > upper_bound)]
        
        analysis.append(f"**{metric.upper()} Outliers:**")
        analysis.append(f"- Outlier count: {len(outliers)}")
        analysis.append(f"- Outlier percentage: {len(outliers)/len(values)*100:.1f}%")
        if len(outliers) > 0:
            analysis.append(f"- Outlier range: {outliers.min():.4f} - {outliers.max():.4f}")
    
    # Анализ по тайлам
    analysis.append("\n### Tile Performance Analysis\n")
    tile_stats = filtered_df.groupby('tile').agg({
        'accuracy': ['mean', 'std'],
        'iou': ['mean', 'std'],
        'f1': ['mean', 'std']
    })
    
    analysis.append("**Best performing tiles:**")
    best_tiles = tile_stats[('iou', 'mean')].sort_values(ascending=False)
    for i, (tile, iou) in enumerate(best_tiles.head(3).items(), 1):
        analysis.append(f"{i}. Tile {tile}: IoU={iou:.4f}")
    
    analysis.append("\n**Most challenging tiles:**")
    worst_tiles = tile_stats[('iou', 'mean')].sort_values(ascending=True)
    for i, (tile, iou) in enumerate(worst_tiles.head(3).items(), 1):
        analysis.append(f"{i}. Tile {tile}: IoU={iou:.4f}")
    
    return "\n".join(analysis)

def generate_local_insights(df):
    """
    Генерирует локальный анализ результатов без использования OpenAI API
    """
    methods = SEGMENTATION_METHODS
    excluded_models = [" grok-4-0709", "gemini-2.5-flash-preview-04-17"]
    true_models = [m for m in df['model'].unique() if m not in NOT_MODELS and m not in excluded_models]
    
    filtered_df = df[df['model'].isin(true_models) & df['method'].isin(methods)]
    
    # Анализируем лучшие результаты
    best_iou = filtered_df.loc[filtered_df['iou'].idxmax()]
    best_accuracy = filtered_df.loc[filtered_df['accuracy'].idxmax()]
    best_f1 = filtered_df.loc[filtered_df['f1'].idxmax()]
    
    # Анализируем худшие результаты
    worst_iou = filtered_df.loc[filtered_df['iou'].idxmin()]
    worst_accuracy = filtered_df.loc[filtered_df['accuracy'].idxmin()]
    worst_f1 = filtered_df.loc[filtered_df['f1'].idxmin()]
    
    # Статистика по моделям
    model_stats = filtered_df.groupby('model').agg({
        'accuracy': ['mean', 'std'],
        'iou': ['mean', 'std'],
        'f1': ['mean', 'std']
    }).round(4)
    
    # Статистика по методам
    method_stats = filtered_df.groupby('method').agg({
        'accuracy': ['mean', 'std'],
        'iou': ['mean', 'std'],
        'f1': ['mean', 'std']
    }).round(4)
    
    # Топ-3 модели по IoU
    top_models_iou = filtered_df.groupby('model')['iou'].mean().sort_values(ascending=False).head(3)
    
    # Топ-3 методы по IoU
    top_methods_iou = filtered_df.groupby('method')['iou'].mean().sort_values(ascending=False).head(3)
    
    analysis = []
    analysis.append("## Key Findings\n")
    analysis.append("### Best Performing Combinations\n")
    analysis.append(f"- **Best IoU:** {best_iou['model']} + {best_iou['method']} (IoU: {best_iou['iou']:.4f})")
    analysis.append(f"- **Best Accuracy:** {best_accuracy['model']} + {best_accuracy['method']} (Accuracy: {best_accuracy['accuracy']:.4f})")
    analysis.append(f"- **Best F1:** {best_f1['model']} + {best_f1['method']} (F1: {best_f1['f1']:.4f})")
    
    analysis.append("\n### Performance Patterns\n")
    analysis.append("**Top 3 Models by IoU:**")
    for i, (model, iou) in enumerate(top_models_iou.items(), 1):
        analysis.append(f"{i}. {model}: IoU={iou:.4f}")
    
    analysis.append("\n**Top 3 Methods by IoU:**")
    for i, (method, iou) in enumerate(top_methods_iou.items(), 1):
        analysis.append(f"{i}. {method}: IoU={iou:.4f}")
    
    analysis.append("\n### Model Performance Analysis\n")
    analysis.append("**Consistency Analysis:**")
    model_consistency = filtered_df.groupby('model')['iou'].std().sort_values()
    most_consistent = model_consistency.head(3)
    least_consistent = model_consistency.tail(3)
    
    analysis.append("**Most Consistent Models:**")
    for i, (model, std) in enumerate(most_consistent.items(), 1):
        analysis.append(f"{i}. {model}: std={std:.4f}")
    
    analysis.append("\n**Least Consistent Models:**")
    for i, (model, std) in enumerate(least_consistent.items(), 1):
        analysis.append(f"{i}. {model}: std={std:.4f}")
    
    analysis.append("\n### Method Performance Analysis\n")
    analysis.append("**Method Strengths and Weaknesses:**")
    method_means = filtered_df.groupby('method')['iou'].mean().sort_values(ascending=False)
    for method, mean_iou in method_means.items():
        method_std = filtered_df[filtered_df['method'] == method]['iou'].std()
        analysis.append(f"- **{method}:** Mean IoU={mean_iou:.4f}, Std={method_std:.4f}")
    
    analysis.append("\n### Recommendations\n")
    analysis.append("**For Production Deployment:**")
    analysis.append(f"- Use {best_iou['model']} with {best_iou['method']} for best IoU performance")
    analysis.append(f"- Consider {most_consistent.index[0]} for consistent results across different tiles")
    
    analysis.append("\n**For Further Research:**")
    analysis.append("- Investigate why certain method-model combinations perform poorly")
    analysis.append("- Explore ensemble methods combining top-performing models")
    analysis.append("- Analyze class-specific performance patterns")
    
    analysis.append("\n**For Model Improvement:**")
    analysis.append("- Focus on improving segmentation methods with lowest performance")
    analysis.append("- Consider data augmentation for challenging tiles")
    analysis.append("- Implement cross-validation for more robust evaluation")
    
    return "\n".join(analysis)

def convert_markdown_to_html(markdown_file, html_file=None):
    """
    Преобразует markdown файл в HTML с поддержкой изображений и таблиц
    """
    if html_file is None:
        html_file = markdown_file.replace('.md', '.html')
    
    # Читаем markdown файл
    with open(markdown_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Настраиваем markdown с расширениями
    md = markdown.Markdown(extensions=[
        'tables',
        'fenced_code',
        'codehilite',
        'toc'
    ])
    
    # Конвертируем в HTML
    html_content = md.convert(md_content)
    
    # Создаем полный HTML документ с CSS стилями
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Final Test Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        h1 {{
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            font-size: 14px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #e8f4fd;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 10px 0;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
        pre {{
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            margin: 20px 0;
            padding-left: 20px;
            color: #555;
        }}
        .metric-highlight {{
            background-color: #e8f5e8;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .success {{
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .info {{
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        @media print {{
            body {{
                background-color: white;
            }}
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
    </div>
</body>
</html>"""
    
    # Сохраняем HTML файл
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    print(f"[INFO] HTML отчет сохранен: {html_file}")
    return html_file

def convert_existing_markdown_to_html(markdown_file_path):
    """
    Конвертирует существующий markdown файл в HTML
    """
    if not os.path.exists(markdown_file_path):
        print(f"[ERROR] Файл не найден: {markdown_file_path}")
        return None
    
    try:
        html_file = convert_markdown_to_html(markdown_file_path)
        print(f"[SUCCESS] HTML отчет создан: {html_file}")
        return html_file
    except Exception as e:
        print(f"[ERROR] Ошибка при конвертации: {e}")
        return None

if __name__ == "__main__":
    print(f"[INFO] Анализируем результаты из: {RESULTS_ROOT}")
    
    try:
        df = collect_metrics()
        print(f"[INFO] Собрано {len(df)} записей метрик")
        
        if df.empty:
            print("[ERROR] Нет данных для анализа!")
            exit(1)
        
        # --- Проверка полноты ---
        missing = check_completeness(df)
        
        # --- Генерация графиков ---
        plots = {}
        for metric in ['accuracy', 'iou', 'f1']:
            plot_path = os.path.join(RESULTS_ROOT, f"plot_{metric}.png")
            try:
                plot_metrics(df, metric, plot_path)
                plots[metric] = plot_path
                print(f"[INFO] График {metric} сохранен: {plot_path}")
            except Exception as e:
                print(f"[ERROR] Ошибка при создании графика {metric}: {e}")
        
        # --- Генерация сводки ---
        try:
            summary_text = generate_gpt_summary(df)
            print("[INFO] Сводка от GPT сгенерирована")
        except Exception as e:
            print(f"[WARN] Ошибка при генерации сводки GPT: {e}")
            summary_text = None
        
        # --- Генерация секции сводки ---
        try:
            summary_section = generate_summary_section(df, RESULTS_ROOT)
            print("[INFO] Секция сводки сгенерирована")
        except Exception as e:
            print(f"[ERROR] Ошибка при генерации секции сводки: {e}")
            summary_section = []
        
        # --- Агрегация по классам ---
        try:
            per_class_agg_section = aggregate_per_class_metrics(df)
            print("[INFO] Агрегация по классам выполнена")
        except Exception as e:
            print(f"[ERROR] Ошибка при агрегации по классам: {e}")
            per_class_agg_section = []
        
        # --- Генерация отчёта ---
        try:
            generate_full_report(df, plots, summary_text, summary_section + per_class_agg_section, missing_combinations=missing)
            print(f"[INFO] Отчет сохранен: {REPORT_MD}")
            
            # Генерируем английскую версию отчета
            generate_full_report_english(df, plots, summary_text, summary_section + per_class_agg_section, missing_combinations=missing)
            print(f"[INFO] English report saved: {os.path.join(RESULTS_ROOT, 'final_report_en.md')}")
            
            # Конвертируем в HTML
            try:
                report_en_md = os.path.join(RESULTS_ROOT, "final_report_en.md")
                if os.path.exists(report_en_md):
                    html_file = convert_markdown_to_html(report_en_md)
                    print(f"[INFO] HTML отчет создан: {html_file}")
                else:
                    print(f"[WARN] Markdown файл не найден: {report_en_md}")
            except Exception as e:
                print(f"[ERROR] Ошибка при конвертации в HTML: {e}")
        except Exception as e:
            print(f"[ERROR] Ошибка при генерации отчета: {e}")
            
    except Exception as e:
        print(f"[ERROR] Критическая ошибка при анализе: {e}")
        import traceback
        traceback.print_exc()
        exit(1) 