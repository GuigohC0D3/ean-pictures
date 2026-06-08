"""
Configuração compartilhada dos testes.

Força o cache em memória ANTES de qualquer import do serviço/app, para que os
testes não criem nem dependam de data/cache.db no disco.
"""

import os
import sys
from pathlib import Path

os.environ["EAN_CACHE_BACKEND"] = "memory"

# Garante que a raiz do projeto está no sys.path (import services, app).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
