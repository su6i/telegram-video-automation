import os
import json
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("⚠️ google-genai not installed. Run: pip install google-genai")
    genai = None

class SmartAgent:
    """
    نسخه Ultimate Automated - مخصوص Gemini 3
    قابلیت اسکن خودکار پروژه و تشخیص وضعیت فعلی (نیمه‌کاره یا جدید)
    """
    
    MODELS_CONFIG = {
        "gemini-3-flash-preview": {"in": 0.50, "out": 3.00, "thinking": "low"},
        "gemini-3-pro-preview": {"in": 2.00, "out": 12.00, "thinking": "high"}
    }
    
    HIERARCHY = ["gemini-3-flash-preview", "gemini-3-pro-preview"]
    
    # پوشه‌هایی که نباید اسکن شوند
    IGNORE_DIRS = {'.git', '.storage', '__pycache__', 'venv', '.ipynb_checkpoints'}
    IGNORE_EXTS = {'.pyc', '.exe', '.png', '.jpg', '.zip'}

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.storage_dir = ".storage/ai_cache"
        self.roadmap_path = os.path.join(self.storage_dir, "roadmap.md")
        self.stats = {"total_cost": 0.0}
        
        os.makedirs(self.storage_dir, exist_ok=True)
        self.project_roadmap = self._load_roadmap()

    def _load_roadmap(self) -> str:
        if os.path.exists(self.roadmap_path):
            with open(self.roadmap_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def _scan_local_files(self) -> str:
        """اسکن تمام فایل‌های پروژه برای درک وضعیت فعلی"""
        project_context = []
        for root, dirs, files in os.walk('.'):
            # حذف پوشه‌های نادیده گرفته شده
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            
            for file in files:
                if any(file.endswith(ext) for ext in self.IGNORE_EXTS):
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        project_context.append(f"--- FILE: {file_path} ---\n{content[:2000]}") # محدودیت برای توکن
                except:
                    continue
        
        return "\n\n".join(project_context)

    def run_task(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        roadmap = self._load_roadmap()
        
        # ۱. فاز تشخیص خودکار (استراتژیک)
        if not roadmap:
            print("🔍 No roadmap found. Scanning local environment...")
            local_code = self._scan_local_files()
            
            if local_code:
                print("🏗️ Existing project detected. Analyzing code for roadmap...")
                strategic_prompt = (
                    f"این کدهای فعلی پروژه من است:\n\n{local_code}\n\n"
                    "بر اساس این‌ها، یک roadmap.md برای ادامه مسیر بساز تا بدانیم چه کارهایی باقی مانده است."
                )
            else:
                print("✨ New project detected. Designing from scratch...")
                strategic_prompt = f"یک پروژه جدید تعریف شده است: {prompt}. یک نقشه راه کامل (roadmap.md) طراحی کن."
            
            # اجرای فاز استراتژیک با مدل Pro
            roadmap_result = self._execute_api("gemini-3-pro-preview", strategic_prompt, "You are a Master Architect.")
            
            self.project_roadmap = roadmap_result
            with open(self.roadmap_path, 'w', encoding='utf-8') as f:
                f.write(roadmap_result)
            print("✅ Roadmap created based on project state.")
            
            # اگر پرومپت کاربر چیزی فراتر از تعریف پروژه بود، دوباره اجرا شود
            if not local_code: return roadmap_result

        # ۲. فاز اجرایی (Executive)
        return self._execute_with_escalation(prompt, context)

    def _execute_with_escalation(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        full_prompt = f"{prompt}\nContext: {json.dumps(context)}" if context else prompt
        sys_instr = f"Follow the project roadmap strictly:\n{self.project_roadmap}"

        for model_name in self.HIERARCHY:
            try:
                result = self._execute_api(model_name, full_prompt, sys_instr)
                if not any(err in result.lower() for err in ["i cannot", "error", "unable"]):
                    return result
                print(f"⚠️ {model_name} gave weak response, escalating...")
            except Exception as e:
                print(f"❌ {model_name} failed: {str(e)[:50]}")
        return "❌ All models failed."

    def _execute_api(self, model_name: str, prompt: str, sys_instr: str) -> str:
        print(f"📡 Requesting {model_name}...")
        config = types.GenerateContentConfig(
            system_instruction=sys_instr,
            temperature=0.7,
            thinking_config=types.ThinkingConfig(
                thinking_level=self.MODELS_CONFIG[model_name]["thinking"]
            )
        )
        response = self.client.models.generate_content(model=model_name, contents=prompt, config=config)
        self._update_cost(model_name, response)
        return response.text

    def _update_cost(self, model_name, response):
        u = response.usage_metadata
        cfg = self.MODELS_CONFIG[model_name]
        cost = (u.prompt_token_count/1e6 * cfg["in"]) + (u.candidates_token_count/1e6 * cfg["out"])
        self.stats["total_cost"] += cost
        print(f"💰 Cost: ${cost:.4f} | Total: ${self.stats['total_cost']:.4f}")