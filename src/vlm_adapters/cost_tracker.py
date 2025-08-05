import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import time

logger = logging.getLogger(__name__)

@dataclass
class CostInfo:
    """Информация о стоимости запроса"""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    total_cost: float
    timestamp: str
    request_id: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None

class CostTracker:
    """Трекер стоимости API запросов"""
    
    def __init__(self, log_file: str = "api_costs.json"):
        self.log_file = log_file
        self.costs = []
        self._load_existing_costs()
        
        # Цены на 1K токенов (в USD) - обновляйте по мере изменения
        self.pricing = {
            "openai": {
                "gpt-4o": {"input": 0.0025, "output": 0.01},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-4o-2024-08-06": {"input": 0.0025, "output": 0.01},
                "gpt-4o-mini-2024-07-18": {"input": 0.00015, "output": 0.0006},
                "gpt-4.1-2025-04-14": {"input": 0.0025, "output": 0.01},
                "gpt-4.1-mini-2025-04-14": {"input": 0.00015, "output": 0.0006},
                "o4-mini": {"input": 0.00015, "output": 0.0006},
                "o3": {"input": 0.00015, "output": 0.0006},
                "o1": {"input": 0.00015, "output": 0.0006},
            },
            "claude": {
                "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
                "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
                "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
                "claude-3-5-haiku-20241022": {"input": 0.00025, "output": 0.00125},
                "claude-4-sonnet-20250219": {"input": 0.003, "output": 0.015},
                "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
            },
            "groq": {
                "grok-2-vision-1212": {"input": 0.0001, "output": 0.0005},
            },
            "gemini": {
                "gemini-2.5-flash-preview-04-17": {"input": 0.000075, "output": 0.0003},
                "gemini-2.5-pro-preview-05-06": {"input": 0.000075, "output": 0.0003},
            },
            "friendli": {
                "Llama-4-Scout-17B-16E-Instruct": {"input": 0.0001, "output": 0.0005},
                "Phi-3.5-vision-instruct": {"input": 0.0001, "output": 0.0005},
            },
            "qwen": {
                "Qwen/QVQ-72B-Preview": {"input": 0.0001, "output": 0.0005},
            },
            "qwen2_5_vl_72b_instruct_awq_friendli": {
                "Qwen2.5-VL-72B-Instruct-AWQ": {"input": 0.0001, "output": 0.0005},
            },
            "qwen_qvq_72b_preview_friendli": {
                "Qwen/QVQ-72B-Preview": {"input": 0.0001, "output": 0.0005},
            },
            "ibm_granite": {
                "ibm-granite/granite-vision-3.2-2b": {"input": 0.0001, "output": 0.0005},
            },
        }
    
    def _load_existing_costs(self):
        """Загружает существующие записи о стоимости"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.costs = [CostInfo(**cost) for cost in data.get('costs', [])]
                    logger.info(f"Загружено {len(self.costs)} записей о стоимости из {self.log_file}")
            except Exception as e:
                logger.error(f"Ошибка при загрузке файла стоимости: {e}")
                self.costs = []
        else:
            self.costs = []
    
    def _save_costs(self):
        """Сохраняет записи о стоимости в файл"""
        try:
            data = {
                'total_requests': len(self.costs),
                'total_cost': sum(cost.total_cost for cost in self.costs),
                'costs': [asdict(cost) for cost in self.costs]
            }
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла стоимости: {e}")
    
    def calculate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Вычисляет стоимость запроса"""
        if provider not in self.pricing:
            logger.warning(f"Неизвестный провайдер: {provider}")
            return 0.0
        
        if model not in self.pricing[provider]:
            logger.warning(f"Неизвестная модель {model} для провайдера {provider}")
            return 0.0
        
        pricing = self.pricing[provider][model]
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        return total_cost
    
    def log_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int, 
                 request_id: Optional[str] = None, additional_info: Optional[Dict[str, Any]] = None):
        """Логирует стоимость запроса"""
        total_cost = self.calculate_cost(provider, model, input_tokens, output_tokens)
        
        cost_info = CostInfo(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_per_1k=self.pricing.get(provider, {}).get(model, {}).get("input", 0),
            output_cost_per_1k=self.pricing.get(provider, {}).get(model, {}).get("output", 0),
            total_cost=total_cost,
            timestamp=datetime.now().isoformat(),
            request_id=request_id,
            additional_info=additional_info
        )
        
        self.costs.append(cost_info)
        self._save_costs()
        
        logger.info(f"Стоимость запроса: {provider}/{model} - ${total_cost:.6f} "
                   f"(input: {input_tokens}, output: {output_tokens})")
        
        return cost_info
    
    def get_total_cost(self, provider: Optional[str] = None, model: Optional[str] = None) -> float:
        """Получает общую стоимость запросов"""
        filtered_costs = self.costs
        
        if provider:
            filtered_costs = [cost for cost in filtered_costs if cost.provider == provider]
        
        if model:
            filtered_costs = [cost for cost in filtered_costs if cost.model == model]
        
        return sum(cost.total_cost for cost in filtered_costs)
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Получает сводку по стоимости"""
        if not self.costs:
            return {"total_cost": 0.0, "total_requests": 0, "by_provider": {}, "by_model": {}}
        
        total_cost = sum(cost.total_cost for cost in self.costs)
        total_requests = len(self.costs)
        
        by_provider = {}
        by_model = {}
        
        for cost in self.costs:
            # По провайдерам
            if cost.provider not in by_provider:
                by_provider[cost.provider] = {"cost": 0.0, "requests": 0}
            by_provider[cost.provider]["cost"] += cost.total_cost
            by_provider[cost.provider]["requests"] += 1
            
            # По моделям
            model_key = f"{cost.provider}/{cost.model}"
            if model_key not in by_model:
                by_model[model_key] = {"cost": 0.0, "requests": 0}
            by_model[model_key]["cost"] += cost.total_cost
            by_model[model_key]["requests"] += 1
        
        return {
            "total_cost": total_cost,
            "total_requests": total_requests,
            "avg_cost_per_request": total_cost / total_requests if total_requests > 0 else 0.0,
            "by_provider": by_provider,
            "by_model": by_model,
            "by_date": {}
        }
    
    def print_summary(self):
        """Выводит сводку по стоимости"""
        summary = self.get_cost_summary()
        
        print("\n" + "="*50)
        print("СВОДКА ПО СТОИМОСТИ API ЗАПРОСОВ")
        print("="*50)
        print(f"Общая стоимость: ${summary['total_cost']:.6f}")
        print(f"Общее количество запросов: {summary['total_requests']}")
        
        if summary['by_provider']:
            print("\nПо провайдерам:")
            for provider, data in summary['by_provider'].items():
                print(f"  {provider}: ${data['cost']:.6f} ({data['requests']} запросов)")
        
        if summary['by_model']:
            print("\nПо моделям:")
            for model, data in summary['by_model'].items():
                print(f"  {model}: ${data['cost']:.6f} ({data['requests']} запросов)")
        print("="*50)

# Глобальный экземпляр трекера
cost_tracker = CostTracker()

def track_api_cost(provider: str, model: str, input_tokens: int, output_tokens: int, 
                   request_id: Optional[str] = None, additional_info: Optional[Dict[str, Any]] = None):
    """Удобная функция для отслеживания стоимости API запроса"""
    return cost_tracker.log_cost(provider, model, input_tokens, output_tokens, request_id, additional_info)

def get_cost_summary():
    """Получает сводку по стоимости"""
    return cost_tracker.get_cost_summary()

def print_cost_summary():
    """Выводит сводку по стоимости"""
    cost_tracker.print_summary() 