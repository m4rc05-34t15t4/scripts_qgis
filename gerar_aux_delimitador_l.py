if __name__ != '__main__':
    raise ImportError("Script procedural para execução direta.")

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


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_SAIDA = "aux_delimitadores_l"
NOME_SAIDA_EDIF_MASSA = "aux_delimitadores_area_edif_massa_dagua_l"

PREFIXO_DELIMITADOR = "delimitador"

NOME_VIA = "via_deslocamento_l"

NOME_MOLDURA = "aux_moldura_a"

NOME_BARRAGEM_A = "infra_barragem_a"
NOME_BARRAGEM_L = "infra_barragem_l"

NOME_FERROVIA = "infra_ferrovia_l"

NOME_DRENAGEM = "elemnat_trecho_drenagem_l"


# ============================================================
# PROJETO
# ============================================================

projeto = QgsProject.instance()

# Remover camadas anteriores se já existirem no projeto para não duplicar
for nome_rem in [NOME_SAIDA, NOME_SAIDA_EDIF_MASSA]:
    camadas_existentes = projeto.mapLayersByName(nome_rem)
    for c_antiga in camadas_existentes:
        projeto.removeMapLayer(c_antiga.id())
        print(f"Camada anterior '{nome_rem}' removida do projeto.")


# ============================================================
# LOCALIZAR CAMADAS
# ============================================================

todas = list(projeto.mapLayers().values())

camadas_origem = []


for camada in todas:

    if not isinstance(camada, QgsVectorLayer):
        continue

    nome = camada.name().lower()

    # Ignorar as próprias camadas de saída se porventura existirem
    if nome in [NOME_SAIDA.lower(), NOME_SAIDA_EDIF_MASSA.lower()]:
        continue


    # --------------------------------------------------------
    # CAMADAS DELIMITADOR*
    # --------------------------------------------------------

    if nome.startswith(PREFIXO_DELIMITADOR.lower()):

        if camada not in camadas_origem:
            camadas_origem.append(camada)


    # --------------------------------------------------------
    # VIA_DESLOCAMENTO_L
    # --------------------------------------------------------

    elif "via_deslocamento" in nome:

        if camada not in camadas_origem:
            camadas_origem.append(camada)


    # --------------------------------------------------------
    # INFRA_BARRAGEM_L
    # --------------------------------------------------------

    elif "infra_barragem" in nome:

        if camada not in camadas_origem:
            camadas_origem.append(camada)


    # --------------------------------------------------------
    # INFRA_FERROVIA_L
    # --------------------------------------------------------

    elif "infra_ferrovia" in nome:

        if camada not in camadas_origem:
            camadas_origem.append(camada)


    # --------------------------------------------------------
    # ELEMNAT_TRECHO_DRENAGEM_L
    # --------------------------------------------------------

    elif "trecho_drenagem" in nome or "drenagem" in nome:

        if camada not in camadas_origem:
            camadas_origem.append(camada)


    # --------------------------------------------------------
    # AUX_MOLDURA_A
    # --------------------------------------------------------

    elif nome == NOME_MOLDURA.lower():

        if camada not in camadas_origem:
            camadas_origem.append(camada)


# ============================================================
# VERIFICAÇÃO
# ============================================================

if not camadas_origem:

    raise Exception(
        "Nenhuma camada de origem foi encontrada."
    )


print("")
print("CAMADAS ENCONTRADAS")
print("----------------------------------------")

for camada in camadas_origem:

    print(
        camada.name(),
        "->",
        QgsWkbTypes.displayString(
            camada.wkbType()
        )
    )

print("----------------------------------------")


# ============================================================
# CRS
# ============================================================

crs = camadas_origem[0].crs()


# ============================================================
# DELIMITADOR MASSA D'ÁGUA PARA TOQUE COM BARRAGEM_A
# ============================================================

linhas_delimitador_massa = []
for c in todas:
    if not isinstance(c, QgsVectorLayer):
        continue
    nome_c = c.name().lower()
    if "delimitador_massa" in nome_c or "delimitador_massa_dagua" in nome_c:
        transf_m = None
        if c.crs() != crs:
            transf_m = QgsCoordinateTransform(c.crs(), crs, projeto)
        for f in c.getFeatures():
            g = f.geometry()
            if g is not None and not g.isEmpty():
                if transf_m is not None:
                    g = QgsGeometry(g)
                    g.transform(transf_m)
                linhas_delimitador_massa.append(g)

geom_uniao_delimitador_massa = None
if linhas_delimitador_massa:
    try:
        geom_uniao_delimitador_massa = QgsGeometry.unaryUnion(linhas_delimitador_massa)
    except Exception as e_union:
        print(f"[Aviso] Falha no unaryUnion das massas d'água: {e_union}")

lat_ref = 0.0
try:
    if crs.isGeographic():
        ext = camadas_origem[0].extent()
        lat_ref = (ext.yMinimum() + ext.yMaximum()) / 2.0
except Exception:
    lat_ref = 0.0

if crs.isGeographic():
    cos_lat = math.cos(math.radians(lat_ref))
    if abs(cos_lat) < 1e-5:
        cos_lat = 1.0
    tolerancia_toque = 2.0 / (111320.0 * cos_lat)  # ~2 metros em graus
else:
    tolerancia_toque = 2.0  # 2 metros


# ============================================================
# CRIAR CAMADAS DE SAÍDA
# ============================================================

saida = QgsVectorLayer(
    "LineString?crs=" + crs.authid(),
    NOME_SAIDA,
    "memory"
)

if not saida.isValid():
    raise Exception(
        "Erro ao criar a camada "
        + NOME_SAIDA
    )

provider = saida.dataProvider()

saida_edif_massa = QgsVectorLayer(
    "LineString?crs=" + crs.authid(),
    NOME_SAIDA_EDIF_MASSA,
    "memory"
)

if not saida_edif_massa.isValid():
    raise Exception(
        "Erro ao criar a camada "
        + NOME_SAIDA_EDIF_MASSA
    )

provider_edif_massa = saida_edif_massa.dataProvider()


# ============================================================
# CAMPOS
# ============================================================

nomes_campos = set()


for camada in camadas_origem:

    for campo in camada.fields():

        nome = campo.name()


        if nome not in nomes_campos:

            attr = [
                QgsField(
                    nome,
                    campo.type(),
                    campo.typeName(),
                    campo.length(),
                    campo.precision()
                )
            ]
            provider.addAttributes(attr)
            provider_edif_massa.addAttributes(attr)

            nomes_campos.add(nome)


# ------------------------------------------------------------
# CAMPO DE ORIGEM
# ------------------------------------------------------------

if "origem" not in nomes_campos:

    attr_origem = [
        QgsField(
            "origem",
            10,
            "text",
            100,
            0
        )
    ]
    provider.addAttributes(attr_origem)
    provider_edif_massa.addAttributes(attr_origem)


saida.updateFields()
saida_edif_massa.updateFields()


# ============================================================
# FILTRO PARA CAMADA AUX_DELIMITADORES_AREA_EDIF_MASSA_DAGUA_L
# ============================================================

ORIGENS_FILTRO_EDIF_MASSA = [
    "infra_barragem_l",
    "infra_barragem_a",
    "aux_moldura_a",
    "delimitador_massa_dagua_l",
    "delimitador_area_edificada_l"
]

def eh_origem_edif_massa(origem_valor):
    if not origem_valor:
        return False
    o = str(origem_valor).lower().strip()
    return any(alvo in o for alvo in ORIGENS_FILTRO_EDIF_MASSA)


# ============================================================
# FUNÇÃO PARA OBTER LINHAS
# ============================================================

def obter_linhas(geom):

    if geom is None:
        return []


    if geom.isEmpty():
        return []


    tipo = QgsWkbTypes.geometryType(
        geom.wkbType()
    )


    # ========================================================
    # GEOMETRIA DE LINHA
    # ========================================================

    if tipo == QgsWkbTypes.LineGeometry:

        resultado = []


        # MULTILINE
        if QgsWkbTypes.isMultiType(
            geom.wkbType()
        ):

            partes = geom.asMultiPolyline()


            for parte in partes:

                if len(parte) >= 2:

                    linha = QgsGeometry.fromPolylineXY(
                        parte
                    )

                    resultado.append(linha)


        # LINESTRING
        else:

            parte = geom.asPolyline()


            if len(parte) >= 2:

                linha = QgsGeometry.fromPolylineXY(
                    parte
                )

                resultado.append(linha)


        return resultado


    # ========================================================
    # GEOMETRIA DE POLÍGONO
    # ========================================================

    if tipo == QgsWkbTypes.PolygonGeometry:

        resultado = []


        # ----------------------------------------------------
        # POLÍGONO SIMPLES
        # ----------------------------------------------------

        if not QgsWkbTypes.isMultiType(
            geom.wkbType()
        ):

            poligono = geom.asPolygon()


            for anel in poligono:

                if len(anel) >= 2:

                    linha = QgsGeometry.fromPolylineXY(
                        anel
                    )

                    resultado.append(linha)


        # ----------------------------------------------------
        # MULTIPOLÍGONO
        # ----------------------------------------------------

        else:

            multipoligono = geom.asMultiPolygon()


            for poligono in multipoligono:

                for anel in poligono:

                    if len(anel) >= 2:

                        linha = QgsGeometry.fromPolylineXY(
                            anel
                        )

                        resultado.append(linha)


        return resultado


    # ========================================================
    # QUALQUER OUTRO TIPO
    # ========================================================

    return []


# ============================================================
# FUNÇÃO PARA OBTER SEGMENTOS DE BARRAGEM QUE TOCAM NA MASSA
# ============================================================

def obter_segmentos_barragem_tocando_massa(geom, geom_massa, tolerancia):
    """
    Para infra_barragem_a (polígono/retângulo), extrai apenas o(s) segmento(s)
    que tocam no delimitador_massa_dagua_l, evitando adicionar os 4 lados do retângulo.
    """
    if geom is None or geom.isEmpty():
        return []

    if geom_massa is None or geom_massa.isEmpty():
        return obter_linhas(geom)

    aneis = []
    tipo = QgsWkbTypes.geometryType(geom.wkbType())
    if tipo == QgsWkbTypes.PolygonGeometry:
        if not QgsWkbTypes.isMultiType(geom.wkbType()):
            poligono = geom.asPolygon()
            for anel in poligono:
                aneis.append(anel)
        else:
            multipoligono = geom.asMultiPolygon()
            for poligono in multipoligono:
                for anel in poligono:
                    aneis.append(anel)
    else:
        return obter_linhas(geom)

    todos_segmentos = []
    for anel in aneis:
        for i in range(len(anel) - 1):
            p1 = anel[i]
            p2 = anel[i + 1]
            if p1 == p2:
                continue
            seg_geom = QgsGeometry.fromPolylineXY([p1, p2])
            todos_segmentos.append((seg_geom, p1, p2))

    if not todos_segmentos:
        return []

    # 1ª Prioridade: Segmento cujos dois vértices tocam no delimitador_massa_dagua_l
    segmentos_dois_toques = []
    for seg_geom, p1, p2 in todos_segmentos:
        g_p1 = QgsGeometry.fromPointXY(p1)
        g_p2 = QgsGeometry.fromPointXY(p2)
        d1 = g_p1.distance(geom_massa)
        d2 = g_p2.distance(geom_massa)
        if d1 <= tolerancia and d2 <= tolerancia:
            segmentos_dois_toques.append(seg_geom)

    if segmentos_dois_toques:
        return segmentos_dois_toques

    # 2ª Prioridade: Segmento que compartilha/intercepta trecho da linha delimitadora
    segmentos_intersecao = []
    for seg_geom, p1, p2 in todos_segmentos:
        try:
            inter = seg_geom.intersection(geom_massa)
            if inter is not None and not inter.isEmpty() and inter.length() > tolerancia:
                segmentos_intersecao.append(seg_geom)
        except Exception:
            pass

    if segmentos_intersecao:
        return segmentos_intersecao

    # 3ª Prioridade: Segmento com vértice que toca no delimitador_massa_dagua_l
    # (escolhe o lado de menor distância média / ponto médio até o delimitador)
    segmentos_um_toque = []
    for seg_geom, p1, p2 in todos_segmentos:
        g_p1 = QgsGeometry.fromPointXY(p1)
        g_p2 = QgsGeometry.fromPointXY(p2)
        d1 = g_p1.distance(geom_massa)
        d2 = g_p2.distance(geom_massa)
        if d1 <= tolerancia or d2 <= tolerancia:
            p_meio = seg_geom.interpolate(seg_geom.length() / 2.0)
            d_meio = p_meio.distance(geom_massa) if p_meio is not None else min(d1, d2)
            segmentos_um_toque.append((d_meio, seg_geom))

    if segmentos_um_toque:
        segmentos_um_toque.sort(key=lambda item: item[0])
        menor_dist = segmentos_um_toque[0][0]
        return [item[1] for item in segmentos_um_toque if item[0] <= menor_dist + tolerancia]

    # Fallback se não encontrar toque com a massa d'água
    return obter_linhas(geom)


# ============================================================
# CONSTRUÇÃO DO POLÍGONO VIRTUAL (MASSA D'ÁGUA + BARRAGEM)
# ============================================================

poligono_virtual_massa = None

camadas_massa_barragem = []
for c in todas:
    if not isinstance(c, QgsVectorLayer):
        continue
    n = c.name().lower()
    if (
        "delimitador_massa" in n
        or "delimitador_massa_dagua" in n
        or "infra_barragem" in n
        or n == NOME_BARRAGEM_A.lower()
        or n == NOME_BARRAGEM_L.lower()
    ):
        if c not in camadas_massa_barragem:
            camadas_massa_barragem.append(c)

if camadas_massa_barragem:
    print("")
    print("============================================")
    print("CONSTRUINDO POLÍGONO VIRTUAL (MASSA + BARRAGEM)")
    print("============================================")
    for c in camadas_massa_barragem:
        print(f"  -> Usando {c.name()} ({c.featureCount()} feições)")

    linhas_massa_barragem = []
    for c in camadas_massa_barragem:
        transf = None
        if c.crs() != crs:
            transf = QgsCoordinateTransform(c.crs(), crs, projeto)

        eh_barr_poly = (
            "infra_barragem" in c.name().lower()
            and c.geometryType() == QgsWkbTypes.PolygonGeometry
        )

        for feat in c.getFeatures():
            g = feat.geometry()
            if g is None or g.isEmpty():
                continue
            if transf is not None:
                g = QgsGeometry(g)
                g.transform(transf)

            # Obter linhas elementares
            if eh_barr_poly:
                sub_linhas = obter_segmentos_barragem_tocando_massa(
                    g,
                    geom_uniao_delimitador_massa,
                    tolerancia_toque
                )
            else:
                sub_linhas = obter_linhas(g)

            for sl in sub_linhas:
                if sl is not None and not sl.isEmpty():
                    linhas_massa_barragem.append(sl)

    if linhas_massa_barragem:
        # Poligonizar as linhas de delimitador_massa + barragem
        try:
            geom_poligonal = QgsGeometry.polygonize(linhas_massa_barragem)
            if geom_poligonal is not None and not geom_poligonal.isEmpty():
                if not geom_poligonal.isGeosValid():
                    geom_valida = geom_poligonal.makeValid()
                    if geom_valida is not None and not geom_valida.isEmpty():
                        geom_poligonal = geom_valida
                poligono_virtual_massa = geom_poligonal
                print("  => Polígono virtual construído com sucesso via polygonize!")
        except Exception as e:
            print(f"  [Aviso] Falha no polygonize: {e}")

        # Se polygonize direto não encontrou anéis fechados perfeitos,
        # tentar fechar linhas abertas ou usar unaryUnion de buffers mínimos
        if poligono_virtual_massa is None or poligono_virtual_massa.isEmpty():
            try:
                # Tentar fechar anéis que tenham pontas muito próximas
                linhas_fechadas = []
                for l in linhas_massa_barragem:
                    if l.isMultipart():
                        partes = l.asMultiPolyline()
                    else:
                        partes = [l.asPolyline()]
                    for p in partes:
                        if len(p) >= 3:
                            if p[0] != p[-1]:
                                p_fechada = list(p) + [p[0]]
                                linhas_fechadas.append(QgsGeometry.fromPolylineXY(p_fechada))
                            else:
                                linhas_fechadas.append(QgsGeometry.fromPolylineXY(p))
                if linhas_fechadas:
                    geom_p2 = QgsGeometry.polygonize(linhas_fechadas)
                    if geom_p2 is not None and not geom_p2.isEmpty():
                        poligono_virtual_massa = geom_p2 if geom_p2.isGeosValid() else geom_p2.makeValid()
                        print("  => Polígono virtual construído com fechamento de anéis!")
            except Exception as e2:
                print(f"  [Aviso] Falha na segunda tentativa de polígono virtual: {e2}")

if poligono_virtual_massa is not None and not poligono_virtual_massa.isEmpty():
    print(f"Polígono virtual ativo: Área aproximada = {poligono_virtual_massa.area():.6f}")
else:
    print("Nenhum polígono virtual de massa+barragem foi formado (drenagens serão preservadas na íntegra).")


# ============================================================
# COPIAR FEIÇÕES
# ============================================================

novas_feicoes = []
novas_feicoes_edif_massa = []


total = 0
criadas = 0
criadas_edif_massa = 0
drenagens_cortadas = 0
drenagens_suprimidas = 0
barragens_a_processadas = 0
barragens_a_segmentos_mantidos = 0


TIPOS_VIA_IGNORAR = [5]

for camada in camadas_origem:

    nome_camada = camada.name().lower()
    eh_drenagem = ("trecho_drenagem" in nome_camada or "drenagem" in nome_camada)
    eh_barragem_a = (
        "infra_barragem" in nome_camada
        and camada.geometryType() == QgsWkbTypes.PolygonGeometry
    )

    print("")
    print(
        "Processando:",
        camada.name()
    )


    campos_origem = camada.fields()
    idx_tipo = (
        campos_origem.lookupField("tipo")
        if hasattr(campos_origem, "lookupField")
        else campos_origem.indexOf("tipo")
    )

    transf_camada = None
    if camada.crs() != crs:
        transf_camada = QgsCoordinateTransform(camada.crs(), crs, projeto)


    for feicao in camada.getFeatures():

        # --- FILTRO PADRÃO DSG: Ignorar arruamentos (tipo = 5) ---
        if "via_deslocamento" in nome_camada and idx_tipo != -1:
            val_tipo = feicao[idx_tipo]
            try:
                if val_tipo is not None and int(val_tipo) in TIPOS_VIA_IGNORAR:
                    continue
            except (ValueError, TypeError):
                if str(val_tipo).strip() == "5":
                    continue

        total += 1


        geom = feicao.geometry()
        if geom is None or geom.isEmpty():
            continue

        if transf_camada is not None:
            geom = QgsGeometry(geom)
            geom.transform(transf_camada)


        # ----------------------------------------------------
        # REGRA CONDICIONAL: ELEMNAT_TRECHO_DRENAGEM_L
        # Cortar ou suprimir qualquer trecho que estiver dentro
        # do polígono virtual formado por massa_dagua + barragem
        # ----------------------------------------------------
        if eh_drenagem and poligono_virtual_massa is not None and not poligono_virtual_massa.isEmpty():
            # Caso 1: A drenagem está totalmente contida dentro do polígono virtual da represa/lago
            if poligono_virtual_massa.contains(geom):
                drenagens_suprimidas += 1
                continue

            # Caso 2: A drenagem intercepta o polígono virtual (entra no lago ou atravessa)
            if geom.intersects(poligono_virtual_massa):
                try:
                    geom_cortada = geom.difference(poligono_virtual_massa)
                    if geom_cortada is None or geom_cortada.isEmpty():
                        drenagens_suprimidas += 1
                        continue
                    geom = geom_cortada
                    drenagens_cortadas += 1
                except Exception as e_corte:
                    print(f"  [Aviso] Falha ao recortar drenagem id={feicao.id()}: {e_corte}")


        # ----------------------------------------------------
        # TRANSFORMAR EM LINHA
        # ----------------------------------------------------

        if eh_barragem_a:
            linhas = obter_segmentos_barragem_tocando_massa(
                geom,
                geom_uniao_delimitador_massa,
                tolerancia_toque
            )
            barragens_a_processadas += 1
            barragens_a_segmentos_mantidos += len(linhas)
        else:
            linhas = obter_linhas(geom)


        # ----------------------------------------------------
        # CRIAR FEIÇÕES
        # ----------------------------------------------------

        for linha in linhas:

            nova = QgsFeature(
                saida.fields()
            )


            # GEOMETRIA
            nova.setGeometry(
                linha
            )


            # ------------------------------------------------
            # ATRIBUTOS
            # ------------------------------------------------

            valores = []


            for campo_saida in saida.fields():

                nome_campo = campo_saida.name()


                # --------------------------------------------
                # Campo origem
                # --------------------------------------------

                if nome_campo == "origem":

                    valores.append(
                        camada.name()
                    )

                    continue


                # --------------------------------------------
                # Campo existente na origem
                # --------------------------------------------

                indice = campos_origem.indexOf(
                    nome_campo
                )


                if indice >= 0:

                    valores.append(
                        feicao[indice]
                    )

                else:

                    valores.append(None)


            nova.setAttributes(
                valores
            )


            novas_feicoes.append(
                nova
            )

            criadas += 1

            # Filtrar feições para a camada aux_delimitadores_area_edif_massa_dagua_l
            if eh_origem_edif_massa(camada.name()):
                nova_edif = QgsFeature(
                    saida_edif_massa.fields()
                )
                nova_edif.setGeometry(
                    linha
                )
                nova_edif.setAttributes(
                    valores
                )
                novas_feicoes_edif_massa.append(
                    nova_edif
                )
                criadas_edif_massa += 1


# ============================================================
# ADICIONAR FEIÇÕES
# ============================================================

if novas_feicoes:

    provider.addFeatures(
        novas_feicoes
    )

saida.updateExtents()


if novas_feicoes_edif_massa:

    provider_edif_massa.addFeatures(
        novas_feicoes_edif_massa
    )

saida_edif_massa.updateExtents()


# ============================================================
# ADICIONAR AO PROJETO
# ============================================================

projeto.addMapLayer(
    saida
)

projeto.addMapLayer(
    saida_edif_massa
)


# ============================================================
# RESULTADO
# ============================================================

print("")
print("============================================")
print("       PROCESSAMENTO CONCLUÍDO")
print("============================================")
print("")
print("Camadas criadas:")
print(f"  - {NOME_SAIDA} ({criadas} linhas)")
print(f"  - {NOME_SAIDA_EDIF_MASSA} ({criadas_edif_massa} linhas)")
print("")
print("Feições de origem processadas:")
print(total)
print("")
print("Linhas criadas na camada geral:")
print(criadas)
if drenagens_cortadas > 0 or drenagens_suprimidas > 0:
    print("")
    print("Drenagens no polígono virtual (massa + barragem):")
    print("  - Trechos de drenagem cortados (mantido apenas fora):", drenagens_cortadas)
    print("  - Trechos de drenagem suprimidos (totalmente internos):", drenagens_suprimidas)
if barragens_a_processadas > 0:
    print("")
    print("Barragens em área (infra_barragem_a):")
    print("  - Feições de barragem processadas:", barragens_a_processadas)
    print("  - Segmentos tocando delimitador_massa_dagua_l adicionados:", barragens_a_segmentos_mantidos)
print("")
print("============================================")