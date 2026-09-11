# -*- coding: utf-8 -*-
"""
Script QGIS: Gerar e Classificar Polígonos de Cobertura Terrestre (gerar_poligonos_cobertura.py)

Descrição:
1. Pega as linhas da camada 'aux_delimitadores_cobertura_l' (que já contêm o recorte externo
   e os contornos de 'area_edificada_area' e 'massa_dagua_area').
2. Poligoniza essas linhas para gerar todas as outras áreas de cobertura da carta.
3. Classifica cada polígono com base nos centróides presentes dentro dele:
   - Ignora centróides de massa d'água e área edificada (já geradas).
   - Cria uma camada de polígonos para cada tipo de centróide (ex: vegetacao_area, etc.).
   - Se o polígono estiver VAZIO (sem centróide), envia para 'flags_areas_vazias_a'.
   - Se o polígono tiver MAIS DE UM centróide, gera pontos em 'flags_centroide_duplo_p'
     e classifica o polígono com base em um dos centróides (evitando buracos na cobertura).
"""

import math
import processing
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsCoordinateTransform
)
from PyQt5.QtCore import QVariant

# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_CAMADA_LINHAS = "aux_delimitadores_cobertura_l"

# Nomes das camadas de flags
NOME_FLAGS_VAZIAS = "flags_areas_vazias_a"
NOME_FLAGS_DUPLOS = "flags_centroide_duplo_p"

# Termos a ignorar (já foram gerados no passo anterior)
TERMOS_IGNORAR_CENTROIDES = [
    "massa_dagua",
    "massa_d_agua",
    "area_edificada",
    "area_construida",
    "edificada",
    "edif"
]

projeto = QgsProject.instance()

# ============================================================
# LOCALIZAR CAMADA DE ENTRADA (LINHAS)
# ============================================================

camadas_linhas = projeto.mapLayersByName(NOME_CAMADA_LINHAS)
if not camadas_linhas:
    raise Exception(
        f"A camada '{NOME_CAMADA_LINHAS}' não foi encontrada no projeto. "
        "Execute primeiro o script 'gerar_aux_delimitadores_cobertura_l.py'."
    )

camada_linhas = camadas_linhas[0]
crs_alvo = camada_linhas.crs()

print(f"Camada de delimitadores: {camada_linhas.name()} ({camada_linhas.featureCount()} feições)")


# ============================================================
# LOCALIZAR CAMADAS DE CENTRÓIDES (EXCLUINDO EDIF E MASSA)
# ============================================================

def eh_centroide_ignorado(nome_camada):
    n = nome_camada.lower().strip()
    return any(t in n for t in TERMOS_IGNORAR_CENTROIDES)

camadas_centroides = []
for c in projeto.mapLayers().values():
    if not isinstance(c, QgsVectorLayer):
        continue
    if c.geometryType() != QgsWkbTypes.PointGeometry:
        continue
    nome_c = c.name().lower()
    # Ignorar camadas de flags existentes
    if "flag" in nome_c:
        continue
    if "centroide" in nome_c:
        if not eh_centroide_ignorado(nome_c):
            camadas_centroides.append(c)

if not camadas_centroides:
    raise Exception(
        "Nenhuma camada de centróide para cobertura terrestre encontrada. "
        "Verifique se as camadas com prefixo 'centroide_' estão carregadas."
    )

print(f"Camadas de centróides identificadas para classificação ({len(camadas_centroides)}):")
for c in camadas_centroides:
    print(f"  -> {c.name()} ({c.featureCount()} pontos)")


# ============================================================
# MAPEAR NOMES DE CAMADAS DE SAÍDA POR TIPO DE CENTRÓIDE
# ============================================================

def extrair_nome_camada_saida(nome_camada_centroide):
    """
    Ex: 'centroide_vegetacao_p' -> 'vegetacao_area'
        'centroide_terreno_exposto_p' -> 'terreno_exposto_area'
    """
    n = nome_camada_centroide.lower().strip()
    if n.startswith("centroide_"):
        n = n[len("centroide_"):]
    if n.endswith("_p"):
        n = n[:-2]
    return f"{n}_area"

# Dicionário mapeando camada de centróide -> nome da camada poligonal destino
mapa_nomes_saida = {}
for c in camadas_centroides:
    mapa_nomes_saida[c.name()] = extrair_nome_camada_saida(c.name())

# ============================================================
# LIMPAR EXECUÇÕES ANTERIORES
# ============================================================

camadas_para_limpar = [NOME_FLAGS_VAZIAS, NOME_FLAGS_DUPLOS] + list(set(mapa_nomes_saida.values()))
for nome_rem in camadas_para_limpar:
    for c_antiga in projeto.mapLayersByName(nome_rem):
        projeto.removeMapLayer(c_antiga.id())
        print(f"Camada anterior '{nome_rem}' removida.")


# ============================================================
# FUNÇÕES DE EXTRAÇÃO E FECHAMENTO DE LINHAS
# ============================================================

def extrair_linhas(geom):
    if geom is None or geom.isEmpty():
        return []
    tipo = QgsWkbTypes.geometryType(geom.wkbType())
    if tipo != QgsWkbTypes.LineGeometry:
        return []
    linhas = []
    if geom.isMultipart():
        for parte in geom.asGeometryCollection():
            if parte is not None and not parte.isEmpty():
                linhas.append(parte)
    else:
        linhas.append(geom)
    return linhas

def fechar_linhas_abertas(lista_linhas, tol_dist):
    linhas_fechadas = []
    fechamentos = 0
    for l in lista_linhas:
        if l is None or l.isEmpty():
            continue
        partes = l.asMultiPolyline() if l.isMultipart() else [l.asPolyline()]
        for p in partes:
            if len(p) >= 3:
                p_ini = p[0]
                p_fim = p[-1]
                if p_ini != p_fim:
                    dist = math.hypot(p_ini.x() - p_fim.x(), p_ini.y() - p_fim.y())
                    if dist <= tol_dist:
                        p_nova = list(p) + [p_ini]
                        linhas_fechadas.append(QgsGeometry.fromPolylineXY(p_nova))
                        fechamentos += 1
                        continue
            linhas_fechadas.append(QgsGeometry.fromPolylineXY(p) if len(p) >= 2 else l)
    if fechamentos > 0:
        print(f"  -> {fechamentos} linha(s) com pontas abertas fechadas automaticamente.")
    return linhas_fechadas

def calcular_area(geom, crs_obj):
    area = geom.area()
    if crs_obj.isGeographic():
        centroide = geom.centroid()
        if centroide is not None and not centroide.isEmpty():
            lat = centroide.asPoint().y()
            area_m2 = area * (111320.0 * math.cos(math.radians(lat))) ** 2
            return area_m2
    return area

def atribuir_geometria_multi(feat, geom):
    if geom is None or geom.isEmpty():
        return
    if not geom.isMultipart():
        g_multi = QgsGeometry(geom)
        g_multi.convertToMultiType()
        feat.setGeometry(g_multi)
    else:
        feat.setGeometry(geom)


# ============================================================
# COLETAR LINHAS E POLIGONIZAR
# ============================================================

# Tolerância para fechamento de pontas
try:
    if crs_alvo.isGeographic():
        ext = camada_linhas.extent()
        lat_ref = (ext.yMinimum() + ext.yMaximum()) / 2.0
        cos_lat = math.cos(math.radians(lat_ref))
        if abs(cos_lat) < 1e-5:
            cos_lat = 1.0
        tol_fechamento = 25.0 / (111320.0 * cos_lat)
    else:
        tol_fechamento = 25.0
except Exception:
    tol_fechamento = 25.0

linhas_todas = []
for f in camada_linhas.getFeatures():
    g = f.geometry()
    sub_l = extrair_linhas(g)
    linhas_todas.extend(sub_l)

print(f"Total de linhas extraídas: {len(linhas_todas)}")
linhas_todas = fechar_linhas_abertas(linhas_todas, tol_fechamento)

# Nodar linhas com unaryUnion
try:
    linhas_unidas = QgsGeometry.unaryUnion(linhas_todas)
    partes_linhas = extrair_linhas(linhas_unidas)
    if not partes_linhas:
        partes_linhas = linhas_todas
except Exception as e_union:
    print(f"  [Aviso] Falha no unaryUnion das linhas: {e_union}")
    partes_linhas = linhas_todas

# Poligonizar
poligonos_brutos = []
try:
    layer_temp = QgsVectorLayer("LineString?crs=" + crs_alvo.authid(), "temp_lines", "memory")
    pr_temp = layer_temp.dataProvider()
    feats_temp = []
    for l in partes_linhas:
        f_tmp = QgsFeature()
        f_tmp.setGeometry(l)
        feats_temp.append(f_tmp)
    pr_temp.addFeatures(feats_temp)

    res = processing.run("native:polygonize", {
        'INPUT': layer_temp,
        'OUTPUT': 'memory:'
    })
    out_l = res.get('OUTPUT')
    if out_l and out_l.isValid():
        for f in out_l.getFeatures():
            g = f.geometry()
            if g and not g.isEmpty():
                poligonos_brutos.append(g)
except Exception as e_proc:
    print(f"  [Aviso] native:polygonize: {e_proc}")

print(f"Polígonos formados a partir dos delimitadores: {len(poligonos_brutos)}")

if not poligonos_brutos:
    raise Exception("Nenhum polígono pôde ser formado com as linhas fornecidas.")


# ============================================================
# PREPARAR ÍNDICE ESPACIAL DE TODOS OS CENTRÓIDES
# ============================================================

idx_centroides = QgsSpatialIndex()
mapa_centroides = {}
ponto_id_counter = 1

for cam in camadas_centroides:
    transf = None
    if cam.crs() != crs_alvo:
        transf = QgsCoordinateTransform(cam.crs(), crs_alvo, projeto)

    for feat in cam.getFeatures():
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        if transf is not None:
            g = QgsGeometry(g)
            g.transform(transf)

        attrs_dict = {}
        for fld in feat.fields():
            attrs_dict[fld.name()] = feat[fld.name()]

        item = {
            "ponto_id": ponto_id_counter,
            "origem_feat_id": feat.id(),
            "camada": cam.name(),
            "camada_obj": cam,
            "geometry": g,
            "atributos": attrs_dict,
            "nome": feat["nome"] if "nome" in feat.fields().names() else None,
            "tipo": feat["tipo"] if "tipo" in feat.fields().names() else None
        }

        f_idx = QgsFeature(ponto_id_counter)
        f_idx.setGeometry(g)
        idx_centroides.addFeature(f_idx)
        mapa_centroides[ponto_id_counter] = item
        ponto_id_counter += 1

print(f"Total de centróides indexados: {len(mapa_centroides)}")


# ============================================================
# RECORTAR POLÍGONOS COINCIDENTES COM ÁREA EDIFICADA E MASSA D'ÁGUA
# (PRESERVANDO ELEMENTOS HIDROGRÁFICOS E ILHAS SOBREPOSTOS NA ÁGUA)
# ============================================================

NOME_POLI_EDIF = "area_edificada_area"
NOME_POLI_MASSA = "massa_dagua_area"

geoms_edif_massa = []
for nome_cam_base in [NOME_POLI_EDIF, NOME_POLI_MASSA]:
    for cam_base in projeto.mapLayersByName(nome_cam_base):
        transf_b = None
        if cam_base.crs() != crs_alvo:
            transf_b = QgsCoordinateTransform(cam_base.crs(), crs_alvo, projeto)
        for f_b in cam_base.getFeatures():
            g_b = f_b.geometry()
            if g_b is None or g_b.isEmpty():
                continue
            if transf_b is not None:
                g_b = QgsGeometry(g_b)
                g_b.transform(transf_b)
            geoms_edif_massa.append(g_b)

mascara_edif_massa = None
if geoms_edif_massa:
    try:
        mascara_edif_massa = QgsGeometry.unaryUnion(geoms_edif_massa)
        print(f"Máscara de recorte (área edificada + massa d'água): {len(geoms_edif_massa)} feição(ões) unida(s).")
    except Exception as e_m:
        print(f"  [Aviso] Falha na união de edif e massa: {e_m}")
        mascara_edif_massa = None

poligonos_filtrados = []
descartados_totalmente_internos = 0
recortados_parciais = 0
mantidos_sobrepostos_massa = 0

bbox_mascara_edif_massa = mascara_edif_massa.boundingBox() if mascara_edif_massa is not None and not mascara_edif_massa.isEmpty() else None

for p in poligonos_brutos:
    if p is None or p.isEmpty():
        continue

    bbox = p.boundingBox()

    # Verificar centróides contidos neste polígono
    candidatos_ids = idx_centroides.intersects(bbox)
    pontos_dentro = [
        mapa_centroides[pid] for pid in candidatos_ids
        if pid in mapa_centroides and p.contains(mapa_centroides[pid]["geometry"])
    ]

    eh_sobreposto_massa = any(
        ("elemento_hidrografico" in pt["camada"].lower() or "ilha" in pt["camada"].lower())
        for pt in pontos_dentro
    )

    # Elementos hidrográficos e ilhas ficam sobrepostos na massa d'água -> NUNCA descartar nem recortar!
    if eh_sobreposto_massa:
        poligonos_filtrados.append(p)
        mantidos_sobrepostos_massa += 1
        continue

    # Se não há máscara ou o bounding box não intercepta, mantém intacto
    if mascara_edif_massa is None or mascara_edif_massa.isEmpty() or not bbox_mascara_edif_massa.intersects(bbox):
        poligonos_filtrados.append(p)
        continue

    # Caso 1: O polígono está totalmente contido dentro de área edificada ou massa d'água
    # (ex: a própria área de água residual gerada pelo contorno fechado) -> Descarta
    if mascara_edif_massa.contains(p):
        descartados_totalmente_internos += 1
        continue

    # Caso 2: Intercepta a máscara (coincide parcialmente) -> Recorta (difference)
    if p.intersects(mascara_edif_massa):
        try:
            p_cortado = p.difference(mascara_edif_massa)
            if p_cortado is None or p_cortado.isEmpty():
                descartados_totalmente_internos += 1
                continue

            # Se gerou partes multipartes, decompõe em polígonos individuais
            partes_cortadas = []
            if p_cortado.isMultipart():
                partes_cortadas = [pt for pt in p_cortado.asGeometryCollection() if pt and not pt.isEmpty()]
            else:
                partes_cortadas = [p_cortado]

            for pt in partes_cortadas:
                if calcular_area(pt, crs_alvo) >= 1.0:
                    poligonos_filtrados.append(pt)
            recortados_parciais += 1

        except Exception as e_corte:
            print(f"  [Aviso] Falha ao recortar polígono: {e_corte}")
            poligonos_filtrados.append(p)
    else:
        poligonos_filtrados.append(p)

print(f"Polígonos após processamento contra área edificada e massa d'água: {len(poligonos_filtrados)}")
print(f"  - Elementos hidrográficos/ilhas preservados sobre a água: {mantidos_sobrepostos_massa}")
print(f"  - Polígonos residuais descartados (dentro da água/cidade): {descartados_totalmente_internos}")
print(f"  - Polígonos recortados na borda: {recortados_parciais}")

poligonos_brutos = poligonos_filtrados


# ============================================================
# PREPARAR CAMADAS DE FLAGS
# ============================================================

# 1. Flags Áreas Vazias (Polígonos sem nenhum centróide)
camada_flags_vazias = QgsVectorLayer(
    "MultiPolygon?crs=" + crs_alvo.authid(),
    NOME_FLAGS_VAZIAS,
    "memory"
)
pr_flags_vazias = camada_flags_vazias.dataProvider()
pr_flags_vazias.addAttributes([
    QgsField("id", QVariant.Int),
    QgsField("area_m2", QVariant.Double, prec=3),
    QgsField("motivo", QVariant.String, len=254)
])
camada_flags_vazias.updateFields()
feicoes_flags_vazias = []

# 2. Flags Centróides Duplos (Pontos)
camada_flags_duplos = QgsVectorLayer(
    "Point?crs=" + crs_alvo.authid(),
    NOME_FLAGS_DUPLOS,
    "memory"
)
pr_flags_duplos = camada_flags_duplos.dataProvider()
pr_flags_duplos.addAttributes([
    QgsField("id", QVariant.Int),
    QgsField("flag_area_id", QVariant.Int),
    QgsField("camada_poligono", QVariant.String, len=100),
    QgsField("camada_ponto", QVariant.String, len=100),
    QgsField("qtd_pontos_area", QVariant.Int),
    QgsField("nome_ponto", QVariant.String, len=100),
    QgsField("tipo_ponto", QVariant.String, len=100),
    QgsField("motivo", QVariant.String, len=254)
])
camada_flags_duplos.updateFields()
feicoes_flags_duplos = []


# ============================================================
# PREPARAR CAMADAS DE POLÍGONOS DE SAÍDA CLASSIFICADAS
# ============================================================

camadas_saida_poligonos = {}

def obter_ou_criar_camada_saida(nome_saida, camada_centroide_origem=None):
    if nome_saida in camadas_saida_poligonos:
        return camadas_saida_poligonos[nome_saida]

    layer = QgsVectorLayer(
        "MultiPolygon?crs=" + crs_alvo.authid(),
        nome_saida,
        "memory"
    )
    pr = layer.dataProvider()

    campos = []
    nomes_adicionados = set()

    # Campo id sequencial primeiro
    campos.append(QgsField("id", QVariant.Int))
    nomes_adicionados.add("id")

    # Copiar TODOS os atributos existentes da camada de centróide de origem
    if camada_centroide_origem is not None:
        for fld in camada_centroide_origem.fields():
            fn = fld.name()
            if fn.lower() not in nomes_adicionados:
                campos.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
                nomes_adicionados.add(fn.lower())

    # Adicionar campos analíticos calculados
    if "area" not in nomes_adicionados:
        campos.append(QgsField("area", QVariant.Double, prec=3))
        nomes_adicionados.add("area")
    if "qtd_centroides" not in nomes_adicionados:
        campos.append(QgsField("qtd_centroides", QVariant.Int))
        nomes_adicionados.add("qtd_centroides")
    if "camada_centroide" not in nomes_adicionados:
        campos.append(QgsField("camada_centroide", QVariant.String, len=100))
        nomes_adicionados.add("camada_centroide")

    pr.addAttributes(campos)
    layer.updateFields()
    camadas_saida_poligonos[nome_saida] = {
        "layer": layer,
        "provider": pr,
        "feicoes": []
    }
    return camadas_saida_poligonos[nome_saida]


# ============================================================
# CLASSIFICAR CADA POLÍGONO
# ============================================================

total_vazios = 0
total_classificados = 0
total_conflitos_multiplos = 0

for idx_poly, poly_geom in enumerate(poligonos_brutos, start=1):
    bbox = poly_geom.boundingBox()
    candidatos_ids = idx_centroides.intersects(bbox)

    pontos_dentro = []
    for pid in candidatos_ids:
        p_info = mapa_centroides.get(pid)
        if not p_info:
            continue
        if poly_geom.contains(p_info["geometry"]):
            pontos_dentro.append(p_info)

    area_calc = round(calcular_area(poly_geom, crs_alvo), 3)

    # CASO 1: Polígono sem centróide -> FLAG ÁREA VAZIA
    if not pontos_dentro:
        total_vazios += 1
        f_vazia = QgsFeature(camada_flags_vazias.fields())
        atribuir_geometria_multi(f_vazia, poly_geom)
        f_vazia.setAttributes([
            len(feicoes_flags_vazias) + 1,
            area_calc,
            "Área delimitada sem centróide de cobertura terrestre."
        ])
        feicoes_flags_vazias.append(f_vazia)
        continue

    # CASO 2: Mais de um centróide -> GERA FLAGS PONTO, MAS CLASSIFICA COM UM DELES
    if len(pontos_dentro) > 1:
        total_conflitos_multiplos += 1
        camadas_envolvidas = ", ".join(sorted(set(p["camada"] for p in pontos_dentro)))

        # Escolhe o centróide principal (critério: nome mais completo ou primeiro)
        pontos_dentro.sort(key=lambda x: len(str(x["nome"] or "")), reverse=True)
        pt_escolhido = pontos_dentro[0]
        nome_camada_destino = mapa_nomes_saida.get(pt_escolhido["camada"], "outras_coberturas_area")

        # Criar as flags de pontos duplicados
        for pt_c in pontos_dentro:
            f_duplo = QgsFeature(camada_flags_duplos.fields())
            f_duplo.setGeometry(pt_c["geometry"])
            f_duplo.setAttributes([
                len(feicoes_flags_duplos) + 1,
                idx_poly,
                nome_camada_destino,
                pt_c["camada"],
                len(pontos_dentro),
                pt_c["nome"],
                pt_c["tipo"],
                f"Polígono com {len(pontos_dentro)} centróides ({camadas_envolvidas}). Classificado como {nome_camada_destino}."
            ])
            feicoes_flags_duplos.append(f_duplo)

    else:
        # Exatamente um centróide
        pt_escolhido = pontos_dentro[0]
        nome_camada_destino = mapa_nomes_saida.get(pt_escolhido["camada"], "outras_coberturas_area")

    # Adicionar o polígono classificado à camada correspondente com TODOS os atributos
    info_saida = obter_ou_criar_camada_saida(nome_camada_destino, pt_escolhido.get("camada_obj"))
    f_poly = QgsFeature(info_saida["layer"].fields())
    atribuir_geometria_multi(f_poly, poly_geom)

    valores_atributos = []
    for fld in info_saida["layer"].fields():
        fn = fld.name()
        if fn == "id":
            valores_atributos.append(len(info_saida["feicoes"]) + 1)
        elif fn == "area":
            valores_atributos.append(area_calc)
        elif fn == "qtd_centroides":
            valores_atributos.append(len(pontos_dentro))
        elif fn == "camada_centroide":
            valores_atributos.append(pt_escolhido["camada"])
        elif fn in pt_escolhido.get("atributos", {}):
            valores_atributos.append(pt_escolhido["atributos"][fn])
        else:
            valores_atributos.append(None)

    f_poly.setAttributes(valores_atributos)
    info_saida["feicoes"].append(f_poly)
    total_classificados += 1


# ============================================================
# SALVAR E ADICIONAR AO PROJETO
# ============================================================

# 1. Camadas poligonais classificadas
for nome_camada, info in camadas_saida_poligonos.items():
    if info["feicoes"]:
        info["provider"].addFeatures(info["feicoes"])
        info["layer"].updateExtents()
        projeto.addMapLayer(info["layer"])
        print(f"Camada '{nome_camada}' criada com {len(info['feicoes'])} polígono(s).")

# 2. Camada de Flags Áreas Vazias (se houver)
if feicoes_flags_vazias:
    pr_flags_vazias.addFeatures(feicoes_flags_vazias)
    camada_flags_vazias.updateExtents()
    projeto.addMapLayer(camada_flags_vazias)
    print(f"Camada de flags '{NOME_FLAGS_VAZIAS}' criada com {len(feicoes_flags_vazias)} polígono(s) vazio(s).")

# 3. Camada de Flags Centróides Duplos (se houver)
if feicoes_flags_duplos:
    pr_flags_duplos.addFeatures(feicoes_flags_duplos)
    camada_flags_duplos.updateExtents()
    projeto.addMapLayer(camada_flags_duplos)
    print(f"Camada de flags '{NOME_FLAGS_DUPLOS}' criada com {len(feicoes_flags_duplos)} ponto(s) em conflito.")


# ============================================================
# RESUMO FINAL
# ============================================================

print("")
print("============================================================")
print("       CLASSIFICAÇÃO DE COBERTURA TERRESTRE CONCLUÍDA       ")
print("============================================================")
print(f"Total de polígonos analisados: {len(poligonos_brutos)}")
print(f"  - Polígonos classificados com sucesso: {total_classificados}")
print(f"  - Polígonos com mais de um centróide (classificados + flag ponto): {total_conflitos_multiplos}")
print(f"  - Áreas vazias sem centróide (flag polígono): {total_vazios}")
print("")
print("Camadas geradas no projeto:")
for nome_c, info in camadas_saida_poligonos.items():
    print(f"  - {nome_c}: {len(info['feicoes'])} feições")
if feicoes_flags_vazias:
    print(f"  - {NOME_FLAGS_VAZIAS}: {len(feicoes_flags_vazias)} feições")
if feicoes_flags_duplos:
    print(f"  - {NOME_FLAGS_DUPLOS}: {len(feicoes_flags_duplos)} feições")
print("============================================================")
