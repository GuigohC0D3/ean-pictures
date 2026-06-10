"""
EANs reais para usar nos benchmarks sem depender de um PDF.

Coletados do catálogo público (VTEX) da Drogaria Globo em 06/2026, agrupados por
categoria. São produtos reais de farmácia (medicamentos, dermocosméticos, higiene
e cuidados com o bebê) — úteis para medir a cobertura de imagem da CDN Cosmos em
itens típicos de drogaria, que costumam ter cobertura diferente de mercearia.

Use via `tests/benchmark_cosmos_cdn.py --source globo`, ou importe diretamente:

    from tests.sample_eans import DROGARIA_GLOBO, all_eans
"""

from __future__ import annotations

# Categoria -> { EAN: nome do produto }. Mantemos o nome para facilitar a leitura
# dos relatórios e a depuração de qual produto ficou sem imagem.
DROGARIA_GLOBO: dict[str, dict[str, str]] = {
    "medicamentos_dipirona": {
        "7896523201887": "Dipirona Monoidratada 1g 10 Comprimidos Cimed",
        "7896004769196": "Dipirona 500mg Genérico EMS 10 Comprimidos",
        "7896004715841": "Dipirona Monoidratada 500mg/ml Gotas Genérico EMS 10ml",
        "7891058002602": "Dipirona 1g 10 Comprimidos Medley",
        "7896004782546": "Dipirona 1g Genérico EMS com 10 Comprimidos",
        "7896714261515": "Dipirona 500mg + Cafeína 65mg Genérico Neo Química 16 Comprimidos",
        "7896004715674": "Dipirona Monoidratada 50mg/ml Solução Oral Genérico EMS 100ml",
    },
    "medicamentos_paracetamol": {
        "7896523209449": "Paracetamol 750mg Cimed com 10 Comprimidos",
        "7896004703596": "Paracetamol 750mg Genérico EMS 20 Comprimidos",
        "7896523209432": "Paracetamol 750mg 20 Comprimidos",
        "7896004700038": "Paracetamol 200mg/ml Gotas Genérico EMS 15ml",
        "7891317192822": "Paracetamol 500mg + Codeína 30mg Genérico Eurofarma 36 Comprimidos",
        "7896004716299": "Paracetamol 100mg/ml Genérico EMS Suspensão Oral 15ml",
        "7896422505390": "Paracetamol 200mg/ml Gotas Genérico Medley 15ml",
    },
    "medicamentos_omeprazol": {
        "7896004701967": "Omeprazol 20mg Genérico EMS 28 Cápsulas",
        "7896714262307": "Omeprazol 20mg Genérico Neo Química 56 Cápsulas",
        "7896714230290": "Omeprazol 20mg Genérico Neo Química 28 Cápsulas",
        "7896422504355": "Omeprazol 20mg Genérico Medley 7 Cápsulas",
    },
    "medicamentos_ibuprofeno": {
        "7899547528619": "Ibuprofeno 600mg 30 Comprimidos Prati Donaduzzi Genérico",
        "7896523201665": "Ibuprofeno 400mg 10 Cápsulas Gel Mole Cimed Genérico",
        "7896422519830": "Ibuprofeno 100mg/ml Gotas Genérico Medley 20ml",
        "7896523227566": "Ibuprofeno Genérico Cimed 100mg Gotas 20ml",
        "7891058002725": "Ibuprofeno Medley 400mg com 10 Cápsulas",
        "7898687730500": "Ibuprofeno 600mg Althaia com 10 Cápsulas",
        "7898700412376": "Ibuprofeno 600mg 10 Cápsulas Vitamedic Genérico",
    },
    "vitaminas_suplementos": {
        "7892828002303": "Suplemento Alimentar Adeforte Turbo 2 Ampolas",
        "7896006219248": "Vitamina D Font D 50.000UI com 4 Comprimidos",
        "7908348616330": "Mega Day Vitamina C 10 Comprimidos Efervescentes",
        "7908348616347": "Mega Day Vitamina C 30 Comprimidos Efervescentes",
        "7898569765194": "Vitamina D3 50.000UI 8 Cápsulas",
        "7897947621077": "Lavitan Vitamina B12 com 100 Comprimidos",
        "0030768026417": "Vitamina E Sundown 400UI 30 Cápsulas",
        "7896714273471": "Vitamina Neo Química Homem 60 Comprimidos",
    },
    "diabetes_endocrino": {
        "7891721201806": "Glifage XR 500mg 30 Comprimidos",
        "7896382709135": "Mounjaro Tirzepatida 5mg Solução Injetável 0,5ml + 4 Canetas",
    },
    "protetor_solar": {
        "3282770206968": "Protetor Solar Avène Emulsão Toque Seco FPS 70 40g",
        "7891317039936": "Kit Protetor Solar OAZ FPS50 200ml + Baby FPS60 125ml",
        "7891317039943": "Kit Protetor Solar OAZ FPS60 200ml + Baby FPS70 125ml",
        "7896902206298": "Protetor Solar Sunless FPS50 200g",
        "7896902287594": "Kit Protetor Solar Sunless FPS50 120g + Kids FPS60 120g",
        "7891010256081": "Protetor Solar Facial Neostrata Minesol FPS70 40g + 120ml",
    },
    "cabelos_shampoo": {
        "7891150075238": "Shampoo Dove Baby Hidratação Glicerinada 400ml",
        "7899706133395": "Shampoo Elseve Hydra Detox 400ml",
        "7898158690401": "Pediderm Shampoo 100ml",
        "7500435154222": "Shampoo Pantene Bambu 200ml",
        "7891142983572": "Shampoo Pielus Forte 400ml",
        "7891024042908": "Shampoo Palmolive Detox 350ml",
    },
    "higiene_bucal": {
        "7896009400049": "Creme Dental Sensodyne Original 50g",
        "7896658005312": "Creme Dental Flogoral Menta 70g",
        "7896015527440": "Creme Dental Parodontax Original 50g",
        "7896009419324": "Creme Dental Sensodyne Original 90g",
        "7891528038704": "Creme Dental Prevent Antiplaca 90g",
        "7896015527457": "Creme Dental Parodontax Flúor 90g",
    },
    "higiene_sabonete": {
        "7896512943750": "Sabonete Líquido Phebo Odor Rosas 320ml",
        "7896685303863": "Sabonete Líquido Kronel 80ml",
        "7898100264124": "Sabonete Antisséptico Sabofen 50g",
        "7896641810510": "Sabonete Íntimo Proctoderm 100ml",
        "7896112408994": "Higicalm Sabonete Íntimo 100ml",
        "7897930778931": "Sabonete Líquido Soapex 100ml",
        "7898100264131": "Sabonete Antisséptico Sabofen 100g",
    },
    "bebe_fraldas": {
        "7896061996849": "Fralda Babysec Premium Mega P 34 Unidades",
        "7896007552818": "Fralda Huggies Máxima Proteção XG 58 Unidades",
        "7896012880340": "Fralda Geriátrica Bigfral Clássica G 7 Unidades",
        "7896012880357": "Fralda Geriátrica Bigfral Clássica XG 7 Unidades",
        "7896061995910": "Fralda Babysec Ultrasec Mega G 32 Unidades",
        "7896061996887": "Fralda Babysec Premium Mega XXG 24 Unidades",
    },
}

# Fontes disponíveis para o benchmark (`--source`).
SOURCES: dict[str, dict[str, dict[str, str]]] = {
    "globo": DROGARIA_GLOBO,
}


def all_eans(source: str = "globo") -> list[str]:
    """Lista achatada de EANs únicos de uma fonte, preservando a ordem de inserção."""
    catalog = SOURCES[source]
    seen: set[str] = set()
    out: list[str] = []
    for category in catalog.values():
        for ean in category:
            if ean not in seen:
                seen.add(ean)
                out.append(ean)
    return out
