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
# CONFIGURAÇÕES DAS CAMADAS
# ============================================================

NOME_CAMADA_ENTRADA = "aux_delimitadores_area_edif_massa_dagua_l"

NOME_SAIDA_MASSA = "massa_dagua_area"
NOME_SAIDA_EDIF = "area_edificada_area"

NOME_FLAGS_PONTOS = "flags_erro_conflitos_p"
NOME_FLAGS_POLIGONOS = "flags_erro_conflitos_a"

TERMOS_CENTROIDE_MASSA = [
    "centroide_massa_dagua",
    "centroide_massa"
]

TERMOS_CENTROIDE_EDIF = [
    "centroide_area_edificada",
    "centroide_area_construida",
    "centroide_edificada",
    "centroide_edif"
]

CENTROIDES_PERMITIDOS_MASSA = [
    "ilha",
    "elemento_hidrografico"
]

CENTROIDES_PERMITIDOS_EDIF = [
    "massa_dagua",
    "massa",
    "ilha",
    "elemento_hidrografico"
]


# ============================================================
# PROJETO E REMOÇÃO DE CAMADAS ANTERIORES
# ============================================================

projeto = QgsProject.instance()

camadas_para_limpar = [
    NOME_SAIDA_MASSA,
    NOME_SAIDA_EDIF,
    NOME_FLAGS_PONTOS,
    NOME_FLAGS_POLIGONOS
]

for nome_rem in camadas_para_limpar:
    for camada_antiga in projeto.mapLayersByName(nome_rem):
        projeto.removeMapLayer(camada_antiga.id())
        print(f"Camada anterior '{nome_rem}' removida do projeto.")


# ============================================================
# LOCALIZAR CAMADA DE ENTRADA
# ============================================================

camadas_entrada = projeto.mapLayersByName(NOME_CAMADA_ENTRADA)

if not camadas_entrada:
    raise Exception(
        f"A camada de entrada '{NOME_CAMADA_ENTRADA}' não foi encontrada no projeto. "
        "Execute o script 'gerar_aux_delimitador_l.py' primeiro."
    )

camada_entrada = camadas_entrada[0]
crs = camada_entrada.crs()

print(f"Camada de entrada: {camada_entrada.name()} ({camada_entrada.featureCount()} feições)")


# ============================================================
# LOCALIZAR TODAS AS CAMADAS DE CENTRÓIDES DO PROJETO
# ============================================================

camadas_centroides_todas = []
for c in projeto.mapLayers().values():
    if not isinstance(c, QgsVectorLayer):
        continue
    if c.geometryType() != QgsWkbTypes.PointGeometry:
        continue
    if "centroide" in c.name().lower():
        camadas_centroides_todas.append(c)

def localizar_camada_pontos(termos_busca):
    for c in camadas_centroides_todas:
        nome = c.name().lower()
        if any(t in nome for t in termos_busca):
            return c
    return None

camada_centroide_massa = localizar_camada_pontos(TERMOS_CENTROIDE_MASSA)
camada_centroide_edif = localizar_camada_pontos(TERMOS_CENTROIDE_EDIF)

def eh_centroide_permitido_massa(nome_camada):
    n = str(nome_camada).lower().strip()
    return any(t in n for t in CENTROIDES_PERMITIDOS_MASSA)

def eh_centroide_permitido_edif(nome_camada):
    n = str(nome_camada).lower().strip()
    return any(t in n for t in CENTROIDES_PERMITIDOS_EDIF)

outras_camadas_centroides_massa = [
    c for c in camadas_centroides_todas
    if c != camada_centroide_massa and not eh_centroide_permitido_massa(c.name())
]

# Para área edificada, centróides de massa d'água/ilha são buracos permitidos
outras_camadas_centroides_edif = [
    c for c in camadas_centroides_todas
    if c != camada_centroide_edif and not eh_centroide_permitido_edif(c.name())
]

print("")
print("Centróides identificados:")
if camada_centroide_massa:
    print(f"  -> Massa d'Água: {camada_centroide_massa.name()}")
if camada_centroide_edif:
    print(f"  -> Área Edificada: {camada_centroide_edif.name()}")
print(f"  -> Conflitos para Massa d'Água checados contra: {[c.name() for c in outras_camadas_centroides_massa]}")
print(f"  -> Conflitos para Área Edificada checados contra: {[c.name() for c in outras_camadas_centroides_edif]}")


# ============================================================
# CALCULAR TOLERÂNCIA ESPACIAL (EM METROS OU GRAUS)
# ============================================================

lat_ref = 0.0
try:
    if crs.isGeographic():
        ext = camada_entrada.extent()
        lat_ref = (ext.yMinimum() + ext.yMaximum()) / 2.0
except Exception:
    lat_ref = 0.0

if crs.isGeographic():
    cos_lat = math.cos(math.radians(lat_ref))
    if abs(cos_lat) < 1e-5:
        cos_lat = 1.0
    tol_fechamento_massa = 25.0 / (111320.0 * cos_lat)
else:
    tol_fechamento_massa = 25.0


# ============================================================
# CRIAR CAMADAS DE FLAGS DE ERRO
# ============================================================

camada_flags_pts = QgsVectorLayer(
    "Point?crs=" + crs.authid(),
    NOME_FLAGS_PONTOS,
    "memory"
)
provider_flags_pts = camada_flags_pts.dataProvider()
provider_flags_pts.addAttributes([
    QgsField("id", QVariant.Int),
    QgsField("flag_area_id", QVariant.Int),
    QgsField("tipo_alvo", QVariant.String, len=50),
    QgsField("camada_conflito", QVariant.String, len=100),
    QgsField("motivo", QVariant.String, len=254),
    QgsField("nome_ponto", QVariant.String, len=100),
    QgsField("area_poligono_m2", QVariant.Double, prec=3)
])
camada_flags_pts.updateFields()

camada_flags_poly = QgsVectorLayer(
    "MultiPolygon?crs=" + crs.authid(),
    NOME_FLAGS_POLIGONOS,
    "memory"
)
provider_flags_poly = camada_flags_poly.dataProvider()
provider_flags_poly.addAttributes([
    QgsField("id", QVariant.Int),
    QgsField("tipo_alvo", QVariant.String, len=50),
    QgsField("camadas_conflito", QVariant.String, len=100),
    QgsField("qtd_conflitos", QVariant.Int),
    QgsField("motivo", QVariant.String, len=254),
    QgsField("area_m2", QVariant.Double, prec=3)
])
camada_flags_poly.updateFields()

todas_flags_pts_feicoes = []
todas_flags_poly_feicoes = []


# ============================================================
# FUNÇÃO PARA EXTRAIR LINHAS ELEMENTARES
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


# ============================================================
# SEPARAR LINHAS POR ORIGEM
# Para massa d'água: apenas delimitadores de massa + barragem + moldura
# Para área edificada: TODAS as feições de aux_delimitadores_area_edif_massa_dagua_l
# ============================================================

idx_origem = camada_entrada.fields().indexOf("origem")

if idx_origem == -1:
    raise Exception(
        f"O campo 'origem' não foi encontrado na camada '{NOME_CAMADA_ENTRADA}'."
    )

def eh_origem_massa(val):
    v = str(val or "").lower().strip()
    return (
        "delimitador_massa" in v
        or "infra_barragem" in v
        or "barragem" in v
        or "moldura" in v
    )

linhas_massa = []
linhas_edif = []

for feicao in camada_entrada.getFeatures():
    geom = feicao.geometry()
    if geom is None or geom.isEmpty():
        continue

    val_origem = feicao[idx_origem]
    sub_linhas = extrair_linhas(geom)

    if not sub_linhas:
        continue

    # Linhas para Massa d'Água
    if eh_origem_massa(val_origem):
        linhas_massa.extend(sub_linhas)

    # Para Área Edificada: usa TODAS as feições da camada de entrada
    # (permite que massas d'água e enclaves de vegetação fechem como buracos)
    linhas_edif.extend(sub_linhas)

print(f"Linhas para Massa d'Água: {len(linhas_massa)}")
print(f"Linhas para Área Edificada (todas as feições): {len(linhas_edif)}")


# ============================================================
# FECHAR PONTAS ABERTAS DE AÇUDES/REPRESAS PRÓXIMAS
# ============================================================

def fechar_linhas_abertas(lista_linhas, tol_dist):
    linhas_fechadas = []
    fechamentos_realizados = 0

    for l in lista_linhas:
        if l is None or l.isEmpty():
            continue

        if l.isMultipart():
            partes = l.asMultiPolyline()
        else:
            partes = [l.asPolyline()]

        for p in partes:
            if len(p) >= 3:
                p_ini = p[0]
                p_fim = p[-1]
                if p_ini != p_fim:
                    dist = math.hypot(p_ini.x() - p_fim.x(), p_ini.y() - p_fim.y())
                    if dist <= tol_dist:
                        p_nova = list(p) + [p_ini]
                        linhas_fechadas.append(QgsGeometry.fromPolylineXY(p_nova))
                        fechamentos_realizados += 1
                        continue
            linhas_fechadas.append(QgsGeometry.fromPolylineXY(p) if len(p) >= 2 else l)

    if fechamentos_realizados > 0:
        print(f"  -> {fechamentos_realizados} açude(s)/represa(s) com pontas abertas foram fechados automaticamente!")

    return linhas_fechadas

linhas_massa = fechar_linhas_abertas(linhas_massa, tol_fechamento_massa)
linhas_edif = fechar_linhas_abertas(linhas_edif, tol_fechamento_massa)


# ============================================================
# FUNÇÃO DE EXTRAÇÃO DE PARTES POLIGONAIS (SEM VALIDAÇÃO GEOS)
# ============================================================

def extrair_partes_poligonais_direto(geom_poligonizada):
    if geom_poligonizada is None or geom_poligonizada.isEmpty():
        return []

    resultado = []
    if geom_poligonizada.isMultipart():
        for parte in geom_poligonizada.asGeometryCollection():
            if parte is not None and not parte.isEmpty():
                resultado.append(parte)
    else:
        resultado.append(geom_poligonizada)

    return resultado


def calcular_area(geom, crs_obj):
    area = geom.area()
    if crs_obj.isGeographic():
        centroide = geom.centroid()
        if centroide is not None and not centroide.isEmpty():
            lat = centroide.asPoint().y()
            area_m2 = area * (111320.0 * math.cos(math.radians(lat))) ** 2
            return area_m2
    return area


# ============================================================
# PREPARAR ÍNDICES DE CENTRÓIDES
# ============================================================

def preparar_indice_centroides(camada, crs_alvo):
    if camada is None:
        return QgsSpatialIndex(), {}

    transf = None
    if camada.crs() != crs_alvo:
        transf = QgsCoordinateTransform(camada.crs(), crs_alvo, projeto)

    pts_info = {}
    idx = QgsSpatialIndex()

    for feat in camada.getFeatures():
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
            "id": feat.id(),
            "geometry": g,
            "atributos": attrs_dict,
            "nome": feat["nome"] if "nome" in feat.fields().names() else None,
            "tipo": feat["tipo"] if "tipo" in feat.fields().names() else None
        }
        f_temp = QgsFeature()
        f_temp.setId(feat.id())
        f_temp.setGeometry(g)
        idx.addFeature(f_temp)
        pts_info[feat.id()] = item

    return idx, pts_info


def preparar_indice_outros_centroides(lista_camadas, crs_alvo):
    idx = QgsSpatialIndex()
    pts_lista = []
    feat_counter = 1

    for cam in lista_camadas:
        if cam is None:
            continue
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

            item = {
                "id": feat.id(),
                "camada": cam.name(),
                "geometry": g,
                "nome": feat["nome"] if "nome" in feat.fields().names() else None
            }
            f_temp = QgsFeature(feat_counter)
            f_temp.setGeometry(g)
            idx.addFeature(f_temp)
            pts_lista.append(item)
            feat_counter += 1

    return idx, pts_lista


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
# POLIGONIZAR E FILTRAR (COM RECORTE DE BURACOS INTERNOS)
# ============================================================

def gerar_poligonos_com_filtro_centroide(
    linhas,
    nome_camada,
    camada_centroide,
    outras_camadas_centroides,
    crs_obj,
    tipo_descricao,
    geometria_buracos_subtrair=None
):
    print("")
    print("------------------------------------------------------------")
    print(f"Processando: {nome_camada} ({tipo_descricao})")
    print("------------------------------------------------------------")

    camada_poligono = QgsVectorLayer(
        "MultiPolygon?crs=" + crs_obj.authid(),
        nome_camada,
        "memory"
    )

    if not camada_poligono.isValid():
        raise Exception(f"Erro ao criar a camada de memória '{nome_camada}'.")

    provider = camada_poligono.dataProvider()

    campos = []
    nomes_adicionados = set()

    # Campo id sequencial primeiro
    campos.append(QgsField("id", QVariant.Int))
    nomes_adicionados.add("id")

    # Copiar TODOS os campos da camada de centróide correspondente
    if camada_centroide is not None:
        for fld in camada_centroide.fields():
            fn = fld.name()
            if fn.lower() not in nomes_adicionados:
                campos.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
                nomes_adicionados.add(fn.lower())

    # Adicionar campos analíticos calculados se não existirem
    if "area" not in nomes_adicionados:
        campos.append(QgsField("area", QVariant.Double, prec=3))
        nomes_adicionados.add("area")
    if "qtd_centroides" not in nomes_adicionados:
        campos.append(QgsField("qtd_centroides", QVariant.Int))
        nomes_adicionados.add("qtd_centroides")

    provider.addAttributes(campos)
    camada_poligono.updateFields()

    if not linhas:
        print(f"  [Aviso] Nenhuma linha para formar polígonos de {tipo_descricao}.")
        projeto.addMapLayer(camada_poligono)
        return camada_poligono, 0, 0, 0

    # 1. Nodar as linhas via unaryUnion
    try:
        uniao = QgsGeometry.unaryUnion(linhas)
        if uniao is not None and not uniao.isEmpty():
            linhas_nodadas = extrair_linhas(uniao)
            if linhas_nodadas:
                linhas = linhas_nodadas
    except Exception as e_union:
        print(f"  [Aviso] Falha ao nodar linhas: {e_union}")

    # 2. Executar o polygonize direto
    poligonos_brutos = []
    try:
        geom_poligonizada = QgsGeometry.polygonize(linhas)
        if geom_poligonizada is not None and not geom_poligonizada.isEmpty():
            poligonos_brutos = extrair_partes_poligonais_direto(geom_poligonizada)
    except Exception as e:
        print(f"  [Aviso] QgsGeometry.polygonize: {e}")

    # 3. Fallback com native:polygonize
    if not poligonos_brutos:
        try:
            layer_temp = QgsVectorLayer("LineString?crs=" + crs_obj.authid(), "temp_lines", "memory")
            pr_temp = layer_temp.dataProvider()
            feats_temp = []
            for l in linhas:
                f = QgsFeature()
                f.setGeometry(l)
                feats_temp.append(f)
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

    total_bruto = len(poligonos_brutos)
    print(f"  Polígonos formados: {total_bruto}")

    if total_bruto == 0:
        print(f"  [Aviso] Nenhum polígono fechado para {tipo_descricao}.")
        projeto.addMapLayer(camada_poligono)
        return camada_poligono, 0, 0, 0

    if camada_centroide is None:
        print(f"  [Aviso] Camada de centróide não encontrada! Mantendo todos os {total_bruto} polígonos.")
        for idx, parte in enumerate(poligonos_brutos, start=1):
            feat = QgsFeature(camada_poligono.fields())
            feat.setGeometry(parte)
            feat.setAttributes([idx, None, tipo_descricao, round(calcular_area(parte, crs_obj), 3), 0])
            provider.addFeature(feat)
        camada_poligono.updateExtents()
        projeto.addMapLayer(camada_poligono)
        return camada_poligono, total_bruto, 0, 0

    # 4. Preparar índices de centróides
    idx_valido, mapa_valido = preparar_indice_centroides(camada_centroide, crs_obj)
    idx_outros, pts_outros = preparar_indice_outros_centroides(outras_camadas_centroides, crs_obj)

    # Preparar lista com TODOS os outros tipos de centróides para detecção de buracos/enclaves
    camadas_para_buracos = [c for c in camadas_centroides_todas if c != camada_centroide]
    _, pts_para_buracos = preparar_indice_outros_centroides(camadas_para_buracos, crs_obj)

    # 5. IDENTIFICAR BURACOS INTERNOS (ex: enclaves de vegetação delimitados dentro da cidade)
    # Se for área edificada (ou massa d'água), polígonos que contêm centróides de vegetação/outro tipo
    # e NÃO contêm o centróide da classe atual são BURACOS internos que devem ser subtraídos.
    buracos_internos = []

    # Mapear índices dos polígonos brutos que contêm o centróide alvo
    indices_com_alvo = set()
    for idx_p, poly_cand in enumerate(poligonos_brutos):
        bbox_c = poly_cand.boundingBox()
        candidatos_ids = idx_valido.intersects(bbox_c)
        tem_alvo = any(
            poly_cand.contains(mapa_valido[p_id]["geometry"])
            for p_id in candidatos_ids
            if p_id in mapa_valido
        )
        if tem_alvo:
            indices_com_alvo.add(idx_p)

    # Avaliar os polígonos que NÃO têm o centróide alvo:
    for idx_p, poly_cand in enumerate(poligonos_brutos):
        if idx_p in indices_com_alvo:
            continue

        bbox_c = poly_cand.boundingBox()

        # Critério 1: Contém algum centróide de outro tipo (ex: vegetação, massa, ilha, etc.)?
        tem_outro = any(
            poly_cand.contains(pt["geometry"])
            for pt in pts_para_buracos
            if bbox_c.intersects(pt["geometry"].boundingBox())
        )

        if tem_outro:
            buracos_internos.append(poly_cand)
        else:
            # Critério 2: Está contido dentro de um polígono que tem centróide alvo (buraco vazio delimitado)?
            for idx_alvo in indices_com_alvo:
                poly_alvo = poligonos_brutos[idx_alvo]
                if poly_alvo.boundingBox().contains(bbox_c):
                    if poly_alvo.contains(poly_cand):
                        buracos_internos.append(poly_cand)
                        break

    if buracos_internos:
        print(f"  -> {len(buracos_internos)} enclave(s)/buraco(s) identificados dentro de {tipo_descricao}!")

    # Unir todos os buracos (massas d'água + enclaves de vegetação/vazios)
    todos_buracos_geoms = []
    if geometria_buracos_subtrair is not None and not geometria_buracos_subtrair.isEmpty():
        todos_buracos_geoms.append(geometria_buracos_subtrair)
    if buracos_internos:
        todos_buracos_geoms.extend(buracos_internos)

    uniao_buracos_total = None
    if todos_buracos_geoms:
        try:
            uniao_buracos_total = QgsGeometry.unaryUnion(todos_buracos_geoms)
        except Exception as e_u_b:
            print(f"  [Aviso] Falha ao unir buracos: {e_u_b}")

    novas_feicoes = []
    areas_vazias_descartadas = 0
    conflitos_descartados = 0

    for idx, poligono_geom in enumerate(poligonos_brutos, start=1):
        bbox = poligono_geom.boundingBox()

        # 5.1. Verificar centróides do tipo correto (CONTENÇÃO ESTRITA)
        # Nunca usar distância/buffer, para não capturar centróides do lado de fora da margem!
        candidatos_ids = idx_valido.intersects(bbox)
        pontos_contidos = []

        for pt_id in candidatos_ids:
            pt_info = mapa_valido.get(pt_id)
            if not pt_info:
                continue
            pt_geom = pt_info["geometry"]

            # Contenção estrita: o centróide DEVE estar dentro da área
            if poligono_geom.contains(pt_geom):
                pontos_contidos.append(pt_info)

        # Sem centróide do tipo correto estritamente dentro -> Não pertence a esta classe!
        # (Se tiver vegetação dentro, é um buraco e não deve gerar erro nem ser criado aqui)
        if not pontos_contidos:
            areas_vazias_descartadas += 1
            continue

        # 5.2. SE FOR ÁREA EDIFICADA: Subtrair os buracos (massa d'água + enclaves de vegetação)
        if uniao_buracos_total is not None and not uniao_buracos_total.isEmpty():
            if poligono_geom.intersects(uniao_buracos_total):
                try:
                    poly_subtraido = poligono_geom.difference(uniao_buracos_total)
                    if poly_subtraido is not None and not poly_subtraido.isEmpty():
                        poligono_geom = poly_subtraido
                except Exception as e_buraco:
                    print(f"  [Aviso] Falha ao subtrair buraco interno: {e_buraco}")

        # 5.3. REGRA DE CONFLITO: Verificar centróides de outros tipos APÓS recortar os buracos
        # Centróides que estavam dentro dos buracos já foram excluídos pelo difference()
        pontos_conflito = []
        for pt_outro in pts_outros:
            pt_g = pt_outro["geometry"]
            if bbox.intersects(pt_g.boundingBox()):
                if poligono_geom.contains(pt_g):
                    pontos_conflito.append(pt_outro)

        # SE AINDA HOUVER CONFLITO (sem estar delimitado como buraco) -> Gera flag de erro!
        if pontos_conflito:
            conflitos_descartados += 1
            camadas_conflitantes_str = ", ".join(sorted(set(p["camada"] for p in pontos_conflito)))
            area_poligono = round(calcular_area(poligono_geom, crs_obj), 3)
            motivo_texto = (
                f"Conflito de centróides: o polígono de {tipo_descricao} contém {len(pontos_conflito)} "
                f"centróide(s) de outro(s) tipo(s) ({camadas_conflitantes_str})."
            )

            id_flag_poly = len(todas_flags_poly_feicoes) + 1

            f_flag_poly = QgsFeature(camada_flags_poly.fields())
            atribuir_geometria_multi(f_flag_poly, poligono_geom)
            f_flag_poly.setAttributes([
                id_flag_poly,
                tipo_descricao,
                camadas_conflitantes_str,
                len(pontos_conflito),
                motivo_texto,
                area_poligono
            ])
            todas_flags_poly_feicoes.append(f_flag_poly)

            for pt_c in pontos_conflito:
                f_flag_pt = QgsFeature(camada_flags_pts.fields())
                f_flag_pt.setGeometry(pt_c["geometry"])
                f_flag_pt.setAttributes([
                    len(todas_flags_pts_feicoes) + 1,
                    id_flag_poly,
                    tipo_descricao,
                    pt_c["camada"],
                    f"Centróide de {pt_c['camada']} (id={pt_c['id']}) impediu a criação da área de {tipo_descricao}.",
                    pt_c.get("nome"),
                    area_poligono
                ])
                todas_flags_pts_feicoes.append(f_flag_pt)

            continue

        # Polígono válido, com buracos recortados e sem conflitos
        pontos_contidos.sort(key=lambda x: len(str(x["nome"] or "")), reverse=True)
        pt_principal = pontos_contidos[0]

        feat = QgsFeature(camada_poligono.fields())
        atribuir_geometria_multi(feat, poligono_geom)
        area_calc = round(calcular_area(poligono_geom, crs_obj), 3)

        valores_atributos = []
        for fld in camada_poligono.fields():
            fn = fld.name()
            if fn == "id":
                valores_atributos.append(len(novas_feicoes) + 1)
            elif fn == "area":
                valores_atributos.append(area_calc)
            elif fn == "qtd_centroides":
                valores_atributos.append(len(pontos_contidos))
            elif fn in pt_principal.get("atributos", {}):
                valores_atributos.append(pt_principal["atributos"][fn])
            else:
                valores_atributos.append(None)

        feat.setAttributes(valores_atributos)
        novas_feicoes.append(feat)

    if novas_feicoes:
        provider.addFeatures(novas_feicoes)

    camada_poligono.updateExtents()
    projeto.addMapLayer(camada_poligono)

    print(f"  => Polígonos válidos mantidos: {len(novas_feicoes)}")
    print(f"  => Áreas vazias/buracos descartados: {areas_vazias_descartadas}")
    print(f"  => Áreas descartadas por CONFLITO real com outros centróides: {conflitos_descartados}")

    return camada_poligono, len(novas_feicoes), areas_vazias_descartadas, conflitos_descartados


# ============================================================
# EXECUTAR: 1º MASSA D'ÁGUA, DEPOIS 2º ÁREA EDIFICADA
# ============================================================

# 1º Passo: Gerar massa_dagua_area
camada_massa, mantidos_massa, vazios_massa, conflitos_massa = gerar_poligonos_com_filtro_centroide(
    linhas_massa,
    NOME_SAIDA_MASSA,
    camada_centroide_massa,
    outras_camadas_centroides_massa,
    crs,
    "massa_dagua"
)

# Coletar a união de todas as massas d'água criadas para subtrair como buracos na área edificada
geometria_uniao_massa = None
if camada_massa and camada_massa.featureCount() > 0:
    geoms_massa = [f.geometry() for f in camada_massa.getFeatures() if f.geometry() and not f.geometry().isEmpty()]
    if geoms_massa:
        try:
            geometria_uniao_massa = QgsGeometry.unaryUnion(geoms_massa)
        except Exception:
            geometria_uniao_massa = None

# 2º Passo: Gerar area_edificada_area usando todas as linhas e subtraindo buracos (água + vegetação)
camada_edif, mantidos_edif, vazios_edif, conflitos_edif = gerar_poligonos_com_filtro_centroide(
    linhas_edif,
    NOME_SAIDA_EDIF,
    camada_centroide_edif,
    outras_camadas_centroides_edif,
    crs,
    "area_edificada",
    geometria_buracos_subtrair=geometria_uniao_massa
)


# ============================================================
# ADICIONAR CAMADAS DE FLAGS AO PROJETO SE HOUVER CONFLITOS REAIS
# ============================================================

if todas_flags_poly_feicoes:
    provider_flags_poly.addFeatures(todas_flags_poly_feicoes)
    camada_flags_poly.updateExtents()
    projeto.addMapLayer(camada_flags_poly)
    print("")
    print(f"[FLAGS ERRO] Camada '{NOME_FLAGS_POLIGONOS}' criada com {len(todas_flags_poly_feicoes)} polígono(s) impedido(s).")

if todas_flags_pts_feicoes:
    provider_flags_pts.addFeatures(todas_flags_pts_feicoes)
    camada_flags_pts.updateExtents()
    projeto.addMapLayer(camada_flags_pts)
    print(f"[FLAGS ERRO] Camada '{NOME_FLAGS_PONTOS}' criada com {len(todas_flags_pts_feicoes)} geometria(s) conflitante(s) impeditiva(s).")


# ============================================================
# RESUMO FINAL
# ============================================================

print("")
print("============================================================")
print("              PROCESSAMENTO CONCLUÍDO COM SUCESSO")
print("============================================================")
print(f"Camada '{NOME_SAIDA_MASSA}':")
print(f"  - Polígonos mantidos: {mantidos_massa}")
print(f"  - Áreas vazias/buracos descartados: {vazios_massa}")
print(f"  - Áreas descartadas por conflito: {conflitos_massa}")
print("")
print(f"Camada '{NOME_SAIDA_EDIF}':")
print(f"  - Polígonos mantidos: {mantidos_edif}")
print(f"  - Áreas vazias/buracos descartados: {vazios_edif}")
print(f"  - Áreas descartadas por conflito: {conflitos_edif}")

if todas_flags_poly_feicoes or todas_flags_pts_feicoes:
    print("")
    print("Camadas de Flags de Erro geradas no projeto:")
    if todas_flags_poly_feicoes:
        print(f"  - {NOME_FLAGS_POLIGONOS} ({len(todas_flags_poly_feicoes)} polígonos)")
    if todas_flags_pts_feicoes:
        print(f"  - {NOME_FLAGS_PONTOS} ({len(todas_flags_pts_feicoes)} pontos)")
else:
    print("")
    print("Nenhum conflito impeditivo encontrado. Nenhuma flag de erro necessária.")

print("============================================================")
