# -*- coding: utf-8 -*-
"""
Script QGIS: Gerar Delimitadores de Cobertura Terrestre (aux_delimitadores_cobertura_l)

Descrição:
1. Pega todas as linhas da camada 'aux_delimitadores_l'.
2. Faz o recorte com as camadas de polígonos 'area_edificada_area' e 'massa_dagua_area',
   mantendo todas as linhas que estão FORA dessas áreas.
3. Extrai os contornos (anéis externos e internos/buracos) dos polígonos de
   'area_edificada_area' e 'massa_dagua_area' e adiciona como delimitadores.
4. Gera a nova camada de linhas: 'aux_delimitadores_cobertura_l'.
"""

import math
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateTransform
)
from PyQt5.QtCore import QVariant

# ============================================================
# CONFIGURAÇÕES DAS CAMADAS
# ============================================================

NOME_LINHAS_ENTRADA = "aux_delimitadores_l"
NOME_POLI_EDIF = "area_edificada_area"
NOME_POLI_MASSA = "massa_dagua_area"

NOME_SAIDA = "aux_delimitadores_cobertura_l"

projeto = QgsProject.instance()

# ============================================================
# LIMPAR EXECUÇÃO ANTERIOR
# ============================================================

for camada_antiga in projeto.mapLayersByName(NOME_SAIDA):
    projeto.removeMapLayer(camada_antiga.id())
    print(f"Camada anterior '{NOME_SAIDA}' removida do projeto.")


# ============================================================
# LOCALIZAR CAMADAS DE ENTRADA
# ============================================================

camadas_linhas = projeto.mapLayersByName(NOME_LINHAS_ENTRADA)
if not camadas_linhas:
    raise Exception(
        f"A camada de entrada '{NOME_LINHAS_ENTRADA}' não foi encontrada no projeto. "
        "Execute o script 'gerar_aux_delimitador_l.py' primeiro."
    )

camada_linhas = camadas_linhas[0]
crs_alvo = camada_linhas.crs()

print(f"Camada de linhas base: {camada_linhas.name()} ({camada_linhas.featureCount()} feições)")

# Localizar camadas de polígonos
camadas_edif = projeto.mapLayersByName(NOME_POLI_EDIF)
camada_edif = camadas_edif[0] if camadas_edif else None

camadas_massa = projeto.mapLayersByName(NOME_POLI_MASSA)
camada_massa = camadas_massa[0] if camadas_massa else None

if not camada_edif and not camada_massa:
    raise Exception(
        f"Nenhuma das camadas de polígonos ('{NOME_POLI_EDIF}' ou '{NOME_POLI_MASSA}') foi encontrada. "
        "Execute 'gerar_poligonos_edif_massa.py' primeiro."
    )


# ============================================================
# FUNÇÕES AUXILIARES DE GEOMETRIA
# ============================================================

def extrair_linhas_de_geometria(geom):
    """Extrai partes de linha elementares (LineString) de qualquer geometria linear."""
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


def extrair_contornos_poligono(geom):
    """
    Extrai todos os anéis (exterior e interiores/buracos)
    de uma geometria poligonal como linhas independentes.
    """
    if geom is None or geom.isEmpty():
        return []

    tipo = QgsWkbTypes.geometryType(geom.wkbType())
    if tipo != QgsWkbTypes.PolygonGeometry:
        return []

    contornos = []

    if not QgsWkbTypes.isMultiType(geom.wkbType()):
        poligono = geom.asPolygon()
        for anel in poligono:
            if len(anel) >= 2:
                contornos.append(QgsGeometry.fromPolylineXY(anel))
    else:
        multipoligono = geom.asMultiPolygon()
        for poligono in multipoligono:
            for anel in poligono:
                if len(anel) >= 2:
                    contornos.append(QgsGeometry.fromPolylineXY(anel))

    return contornos


# ============================================================
# COLETAR E UNIR POLÍGONOS DE RECORTE (ÁREA EDIFICADA + MASSA D'ÁGUA)
# ============================================================

geometrias_poligonos = []
contornos_edif = []
contornos_massa = []

# Processar Área Edificada
if camada_edif:
    transf_edif = None
    if camada_edif.crs() != crs_alvo:
        transf_edif = QgsCoordinateTransform(camada_edif.crs(), crs_alvo, projeto)

    for f in camada_edif.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        if transf_edif is not None:
            g = QgsGeometry(g)
            g.transform(transf_edif)

        geometrias_poligonos.append(g)
        contornos = extrair_contornos_poligono(g)
        contornos_edif.extend(contornos)

    print(f"Camada '{NOME_POLI_EDIF}': {len(contornos_edif)} contorno(s) extraído(s).")
else:
    print(f"[Aviso] Camada '{NOME_POLI_EDIF}' não encontrada, prosseguindo sem ela.")

# Processar Massa d'Água
if camada_massa:
    transf_massa = None
    if camada_massa.crs() != crs_alvo:
        transf_massa = QgsCoordinateTransform(camada_massa.crs(), crs_alvo, projeto)

    for f in camada_massa.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        if transf_massa is not None:
            g = QgsGeometry(g)
            g.transform(transf_massa)

        geometrias_poligonos.append(g)
        contornos = extrair_contornos_poligono(g)
        contornos_massa.extend(contornos)

    print(f"Camada '{NOME_POLI_MASSA}': {len(contornos_massa)} contorno(s) extraído(s).")
else:
    print(f"[Aviso] Camada '{NOME_POLI_MASSA}' não encontrada, prosseguindo sem ela.")

# Criar a máscara única dos polígonos
mascara_unida = None
if geometrias_poligonos:
    try:
        mascara_unida = QgsGeometry.unaryUnion(geometrias_poligonos)
        print("União das máscaras poligonais concluída com sucesso.")
    except Exception as e_union:
        print(f"[Aviso] Falha no unaryUnion dos polígonos: {e_union}")
        mascara_unida = None


# ============================================================
# CRIAR CAMADA DE SAÍDA
# ============================================================

camada_saida = QgsVectorLayer(
    "LineString?crs=" + crs_alvo.authid(),
    NOME_SAIDA,
    "memory"
)

if not camada_saida.isValid():
    raise Exception(f"Erro ao criar a camada de memória '{NOME_SAIDA}'.")

provider_saida = camada_saida.dataProvider()

# Copiar estrutura de atributos da camada de linhas original
campos_saida = [QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision()) for f in camada_linhas.fields()]

# Garantir que temos o campo 'origem'
nomes_campos_saida = [f.name().lower() for f in campos_saida]
if "origem" not in nomes_campos_saida:
    campos_saida.append(QgsField("origem", QVariant.String, len=100))

provider_saida.addAttributes(campos_saida)
camada_saida.updateFields()

idx_origem = camada_saida.fields().indexOf("origem")
idx_id = camada_saida.fields().indexOf("id")


# ============================================================
# RECORTAR LINHAS (MANTER APENAS O QUE ESTÁ FORA DOS POLÍGONOS)
# ============================================================

novas_feicoes = []
contador_feicoes = 0

linhas_mantidas_total = 0
linhas_cortadas = 0
linhas_suprimidas_internas = 0

bbox_mascara = mascara_unida.boundingBox() if mascara_unida is not None and not mascara_unida.isEmpty() else None

for feat_linha in camada_linhas.getFeatures():
    geom_l = feat_linha.geometry()
    if geom_l is None or geom_l.isEmpty():
        continue

    val_origem = str(feat_linha[idx_origem] or "").lower() if idx_origem != -1 else ""
    eh_elemento_hidro = "elemento_hidrografico" in val_origem

    # Linhas de delimitador_elemento_hidrografico_l não devem ser apagadas pelo clipe (mesmo dentro de massa d'água)
    if eh_elemento_hidro:
        partes = extrair_linhas_de_geometria(geom_l)
        for p in partes:
            contador_feicoes += 1
            f_nova = QgsFeature(camada_saida.fields())
            f_nova.setGeometry(p)
            attrs = list(feat_linha.attributes())
            if idx_id != -1 and len(attrs) > idx_id:
                attrs[idx_id] = contador_feicoes
            f_nova.setAttributes(attrs)
            novas_feicoes.append(f_nova)
            linhas_mantidas_total += 1
        continue

    # Se não há máscara ou se a linha nem intercepta o bounding box da máscara:
    # Está 100% fora -> mantém inteira diretamente
    if mascara_unida is None or mascara_unida.isEmpty() or not bbox_mascara.intersects(geom_l.boundingBox()):
        partes = extrair_linhas_de_geometria(geom_l)
        for p in partes:
            contador_feicoes += 1
            f_nova = QgsFeature(camada_saida.fields())
            f_nova.setGeometry(p)
            attrs = list(feat_linha.attributes())
            if idx_id != -1 and len(attrs) > idx_id:
                attrs[idx_id] = contador_feicoes
            f_nova.setAttributes(attrs)
            novas_feicoes.append(f_nova)
            linhas_mantidas_total += 1
        continue

    # Linha totalmente contida dentro da área edificada ou massa d'água -> Suprime
    if mascara_unida.contains(geom_l):
        linhas_suprimidas_internas += 1
        continue

    # Se intercepta a máscara -> Faz a diferença (mantém apenas o que está fora)
    if geom_l.intersects(mascara_unida):
        try:
            geom_fora = geom_l.difference(mascara_unida)
            if geom_fora is None or geom_fora.isEmpty():
                linhas_suprimidas_internas += 1
                continue

            partes = extrair_linhas_de_geometria(geom_fora)
            if not partes:
                linhas_suprimidas_internas += 1
                continue

            linhas_cortadas += 1
            for p in partes:
                contador_feicoes += 1
                f_nova = QgsFeature(camada_saida.fields())
                f_nova.setGeometry(p)
                attrs = list(feat_linha.attributes())
                if idx_id != -1 and len(attrs) > idx_id:
                    attrs[idx_id] = contador_feicoes
                f_nova.setAttributes(attrs)
                novas_feicoes.append(f_nova)
                linhas_mantidas_total += 1

        except Exception as e_diff:
            print(f"  [Aviso] Falha ao recortar linha id={feat_linha.id()}: {e_diff}")
            # Em caso de falha geométrica, mantém a original
            partes = extrair_linhas_de_geometria(geom_l)
            for p in partes:
                contador_feicoes += 1
                f_nova = QgsFeature(camada_saida.fields())
                f_nova.setGeometry(p)
                attrs = list(feat_linha.attributes())
                if idx_id != -1 and len(attrs) > idx_id:
                    attrs[idx_id] = contador_feicoes
                f_nova.setAttributes(attrs)
                novas_feicoes.append(f_nova)
                linhas_mantidas_total += 1
    else:
        # Não intercepta
        partes = extrair_linhas_de_geometria(geom_l)
        for p in partes:
            contador_feicoes += 1
            f_nova = QgsFeature(camada_saida.fields())
            f_nova.setGeometry(p)
            attrs = list(feat_linha.attributes())
            if idx_id != -1 and len(attrs) > idx_id:
                attrs[idx_id] = contador_feicoes
            f_nova.setAttributes(attrs)
            novas_feicoes.append(f_nova)
            linhas_mantidas_total += 1


# ============================================================
# ADICIONAR OS CONTORNOS DOS POLÍGONOS COMO DELIMITADORES
# ============================================================

def criar_feicoes_contorno(lista_contornos, nome_origem):
    feicoes = []
    global contador_feicoes
    for c in lista_contornos:
        if c is None or c.isEmpty():
            continue
        contador_feicoes += 1
        f = QgsFeature(camada_saida.fields())
        f.setGeometry(c)
        valores = [None] * len(camada_saida.fields())
        if idx_id != -1:
            valores[idx_id] = contador_feicoes
        if idx_origem != -1:
            valores[idx_origem] = nome_origem
        f.setAttributes(valores)
        feicoes.append(f)
    return feicoes

feicoes_contorno_edif = criar_feicoes_contorno(contornos_edif, NOME_POLI_EDIF)
feicoes_contorno_massa = criar_feicoes_contorno(contornos_massa, NOME_POLI_MASSA)

novas_feicoes.extend(feicoes_contorno_edif)
novas_feicoes.extend(feicoes_contorno_massa)


# ============================================================
# REPOR LINHAS DA CAMADA DELIMITADOR_ELEMENTO_HIDROGRAFICO_L
# (Mesmo que estejam sobrepostas/dentro de massa_dagua_area)
# ============================================================

NOME_DELIMITADOR_HIDRO = "delimitador_elemento_hidrografico_l"
linhas_hidro_adicionadas = 0

camadas_hidro = [
    c for c in projeto.mapLayers().values()
    if isinstance(c, QgsVectorLayer) and c.name().lower() == NOME_DELIMITADOR_HIDRO
]

for c in camadas_hidro:
    # Se não for a própria camada de entrada ou saída
    if c.name().lower() not in [camada_linhas.name().lower(), NOME_SAIDA.lower()]:
        transf_h = None
        if c.crs() != crs_alvo:
            transf_h = QgsCoordinateTransform(c.crs(), crs_alvo, projeto)

        for feat_h in c.getFeatures():
            g_h = feat_h.geometry()
            if g_h is None or g_h.isEmpty():
                continue
            if transf_h is not None:
                g_h = QgsGeometry(g_h)
                g_h.transform(transf_h)

            partes = extrair_linhas_de_geometria(g_h)
            for p in partes:
                contador_feicoes += 1
                f_nova = QgsFeature(camada_saida.fields())
                f_nova.setGeometry(p)
                valores = [None] * len(camada_saida.fields())
                if idx_id != -1:
                    valores[idx_id] = contador_feicoes
                if idx_origem != -1:
                    valores[idx_origem] = NOME_DELIMITADOR_HIDRO
                f_nova.setAttributes(valores)
                novas_feicoes.append(f_nova)
                linhas_hidro_adicionadas += 1

if linhas_hidro_adicionadas > 0:
    print(f"Linhas da camada '{NOME_DELIMITADOR_HIDRO}' repostas: {linhas_hidro_adicionadas}")


# ============================================================
# SALVAR NA CAMADA E ADICIONAR AO PROJETO
# ============================================================

if novas_feicoes:
    provider_saida.addFeatures(novas_feicoes)

camada_saida.updateExtents()
projeto.addMapLayer(camada_saida)


# ============================================================
# RESUMO FINAL
# ============================================================

print("")
print("============================================================")
print(f"       CAMADA '{NOME_SAIDA}' GERADA COM SUCESSO")
print("============================================================")
print(f"Linhas mantidas fora das áreas edificadas e massas d'água: {linhas_mantidas_total}")
print(f"  - Linhas recortadas na borda: {linhas_cortadas}")
print(f"  - Linhas suprimidas (totalmente internas): {linhas_suprimidas_internas}")
print(f"Contornos de '{NOME_POLI_EDIF}' adicionados: {len(feicoes_contorno_edif)}")
print(f"Contornos de '{NOME_POLI_MASSA}' adicionados: {len(feicoes_contorno_massa)}")
print(f"Total de feições na camada '{NOME_SAIDA}': {len(novas_feicoes)}")
print("============================================================")
