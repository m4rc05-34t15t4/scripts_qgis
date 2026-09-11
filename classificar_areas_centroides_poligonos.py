# ============================================================
# CLASSIFICAÇÃO DE POLÍGONOS A PARTIR DE CENTROIDES
#
# Compatível com QGIS 3.24+
#
# Melhorias:
# - Índice espacial para localizar polígonos rapidamente
# - Polígonos carregados uma única vez em memória
# - Consulta das restrições reais do PostgreSQL
# - Respeita DEFAULT do PostgreSQL
# - NOT NULL sem DEFAULT:
#       numérico -> 9999
#       texto    -> desconhecido
#       booleano -> False
# - Evita duplicação por hash/geometria
# - Não imprime cada "SEM POLÍGONO"
# - Mostra progresso periodicamente
# - Erros são mostrados imediatamente
# - centroide_ilha_p -> elemnat_ilha_a
# ============================================================


from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsCoordinateTransform,
    QgsDataSourceUri,
    QgsProviderRegistry,
    NULL
)

import hashlib
import math
import time

try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import (
        QMessageBox,
        QProgressDialog,
        QApplication
    )
except ImportError:
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import (
            QMessageBox,
            QProgressDialog,
            QApplication
        )
    except ImportError:
        Qt = None
        QMessageBox = None
        QProgressDialog = None
        QApplication = None

try:
    from qgis.utils import iface
except Exception:
    iface = None


# ============================================================
# MODO DE OPERAÇÃO
# ============================================================

# Se True, gera camadas temporárias (em memória) no QGIS com os polígonos
# classificados para conferência, SEM gravar diretamente no banco de dados.
# Se False, grava diretamente nas camadas de destino do banco.
GERAR_CAMADA_TEMPORARIA = True

# Prefixo para os nomes das camadas temporárias geradas no QGIS
PREFIXO_TEMP = "temp_"

# Nome da camada de polígonos não classificados (flags de verificação)
NOME_CAMADA_NAO_CLASSIFICADAS = "area_sem_centroide"

# Nome do grupo no QGIS onde ficarão todas as camadas geradas
NOME_GRUPO = "Areas_cobertura_terrestre"


# ============================================================
# CONFIGURAÇÃO DE CLASSES E NOMES CANÔNICOS
# ============================================================

CONFIG_CLASSES = {
    "vegetacao": {
        "rotulo": "Vegetação",
        "tipo_classe": "base",
        "palavras_chave": ["centroide_vegetacao", "vegetacao", "vegetal", "floresta", "mata", "cerrado", "pastagem", "cultura"],
        "nomes_possiveis_destino": ["cobter_vegetacao_a", "vegetacao_a"],
        "nome_padrao_destino": "cobter_vegetacao_a",
        "nome_temp": f"{PREFIXO_TEMP}cobter_vegetacao_a"
    },
    "terreno_exposto": {
        "rotulo": "Terreno Exposto / Sem Vegetação",
        "tipo_classe": "base",
        "palavras_chave": [
            "centroide_terreno_exposto", "terreno_exposto", "solo_exposto",
            "sem_vegetacao", "sem_veg", "area_sem_vegetacao", "rocha_exposta",
            "duna", "praia", "areal", "areia"
        ],
        "nomes_possiveis_destino": [
            "cobter_area_sem_vegetacao_a", "cobter_terreno_exposto_a",
            "terreno_exposto_a", "area_sem_vegetacao_a",
            "cobter_solo_exposto_a", "solo_exposto_a"
        ],
        "nome_padrao_destino": "cobter_area_sem_vegetacao_a",
        "nome_temp": f"{PREFIXO_TEMP}cobter_area_sem_vegetacao_a"
    },
    "massa_dagua": {
        "rotulo": "Massa d'Água",
        "tipo_classe": "base",
        "palavras_chave": [
            "centroide_massa_dagua", "centroide_massa_d_agua",
            "massa_dagua", "massa_d_agua"
        ],
        "nomes_possiveis_destino": ["cobter_massa_dagua_a", "massa_dagua_a"],
        "nome_padrao_destino": "cobter_massa_dagua_a",
        "nome_temp": f"{PREFIXO_TEMP}cobter_massa_dagua_a"
    },
    "area_edificada": {
        "rotulo": "Área Edificada",
        "tipo_classe": "base",
        "palavras_chave": [
            "centroide_area_edificada", "centroide_area_construida",
            "area_edificada", "area_construida", "edificada", "construida",
            "edificacao", "edificacoes"
        ],
        "nomes_possiveis_destino": [
            "cobter_area_edificada_a", "area_edificada_a",
            "cobter_area_construida_a", "area_construida_a"
        ],
        "nome_padrao_destino": "cobter_area_edificada_a",
        "nome_temp": f"{PREFIXO_TEMP}cobter_area_edificada_a"
    },
    "ilha": {
        "rotulo": "Ilha",
        "tipo_classe": "sobreposicao",
        "palavras_chave": ["centroide_ilha", "ilha"],
        "nomes_possiveis_destino": ["elemnat_ilha_a", "ilha_a"],
        "nome_padrao_destino": "elemnat_ilha_a",
        "nome_temp": f"{PREFIXO_TEMP}elemnat_ilha_a"
    },
    "ocupacao_solo": {
        "rotulo": "Ocupação do Solo",
        "tipo_classe": "sobreposicao",
        "palavras_chave": ["centroide_ocupacao_solo", "centroide_uso_solo"],
        "nomes_possiveis_destino": [
            "aux_ocupacao_solo_a", "ocupacao_solo_a",
            "cobter_ocupacao_solo_a", "uso_ocupacao_solo_a"
        ],
        "nome_padrao_destino": "aux_ocupacao_solo_a",
        "nome_temp": f"{PREFIXO_TEMP}aux_ocupacao_solo_a"
    }
}


# ============================================================
# CAMADA DOS POLÍGONOS ORIGINAIS
# ============================================================

NOME_CAMADA_POLIGONOS = "Polígonos"


# ============================================================
# CONFIGURAÇÕES
# ============================================================

# Quantos centroides processar antes de mostrar progresso
INTERVALO_PROGRESSO = 500

# Quantos caracteres usar no hash
TAMANHO_HASH = 12

# Precisão numérica utilizada no hash
PRECISAO_HASH = 3


# ============================================================
# VALORES PADRÃO
# ============================================================

VALORES_PADRAO = {

    "numerico": 9999,

    "texto": "desconhecido",

    "booleano": False,

}


# ============================================================
# PROJETO
# ============================================================

projeto = QgsProject.instance()


# ============================================================
# FUNÇÕES DE NORMALIZAÇÃO E IDENTIFICAÇÃO DE CAMADAS
# ============================================================

def normalizar_nome(texto):
    if not texto:
        return ""
    t = str(texto).lower()
    t = (
        t.replace("á", "a").replace("ã", "a").replace("â", "a")
         .replace("é", "e").replace("ê", "e")
         .replace("í", "i")
         .replace("ó", "o").replace("ô", "o").replace("õ", "o")
         .replace("ú", "u")
         .replace("ç", "c")
    )
    t = t.replace(" ", "_").replace("'", "_").replace("-", "_")
    return t


def identificar_classe(nome):
    if not nome:
        return None
    norm = normalizar_nome(nome)

    # Ignora camadas que claramente NÃO são centroides
    termos_ignorar = (
        "ponto_cotado", "vertice", "delimitador", "poligono",
        "drenagem", "trecho", "linha", "deslocamento", "ferrovia", "barragem"
    )
    if any(ign in norm for ign in termos_ignorar):
        return None

    # 1. Massa d'água
    if "massa_dagua" in norm or "massa_d_agua" in norm:
        return "massa_dagua"

    # 2. Terreno Exposto / Sem Vegetação
    if any(k in norm for k in ("terreno_exposto", "solo_exposto", "sem_vegetacao", "sem_veg", "rocha_exposta", "duna", "praia", "areal")):
        return "terreno_exposto"

    # 3. Vegetação
    if any(k in norm for k in ("vegeta", "florest", "mata", "cerrado", "pastagem", "cultura")):
        return "vegetacao"

    # 4. Área Edificada
    if any(k in norm for k in ("edifica", "construi", "edific")):
        return "area_edificada"

    # 5. Ilha (sobreposição)
    if "ilha" in norm:
        return "ilha"

    # 6. Ocupação do Solo (apenas se for especificamente centroide de ocupação)
    if "centroide_ocupacao_solo" in norm or "centroide_uso_solo" in norm:
        return "ocupacao_solo"

    return None


def encontrar_camada(nome):
    if not nome:
        return None
    nome_norm = normalizar_nome(nome)
    for camada in projeto.mapLayers().values():
        if not isinstance(camada, QgsVectorLayer):
            continue
        if normalizar_nome(camada.name()) == nome_norm:
            return camada
    return None


# ============================================================
# NORMALIZAR VALOR PARA HASH
# ============================================================

def normalizar_valor(valor):

    if valor is None:
        return ""

    if valor is NULL:
        return ""

    if isinstance(valor, float):

        if math.isnan(valor):
            return "nan"

        return str(
            round(
                valor,
                PRECISAO_HASH
            )
        )

    if isinstance(
        valor,
        (list, tuple)
    ):

        return "|".join(
            normalizar_valor(v)
            for v in valor
        )

    return str(valor)


# ============================================================
# HASH DA GEOMETRIA
# ============================================================

def hash_geometria(geometria):

    if (
        geometria is None
        or geometria.isEmpty()
    ):
        return ""

    partes = []


    # --------------------------------------------------------
    # ÁREA
    # --------------------------------------------------------

    try:

        partes.append(
            "AREA=" +
            normalizar_valor(
                geometria.area()
            )
        )

    except Exception:
        pass


    # --------------------------------------------------------
    # BOUNDING BOX
    # --------------------------------------------------------

    try:

        bbox = geometria.boundingBox()

        partes.extend([

            "XMIN=" +
            normalizar_valor(
                bbox.xMinimum()
            ),

            "YMIN=" +
            normalizar_valor(
                bbox.yMinimum()
            ),

            "XMAX=" +
            normalizar_valor(
                bbox.xMaximum()
            ),

            "YMAX=" +
            normalizar_valor(
                bbox.yMaximum()
            )

        ])

    except Exception:
        pass


    # --------------------------------------------------------
    # PRIMEIRO / ÚLTIMO VÉRTICE
    # --------------------------------------------------------

    try:

        vertices = list(
            geometria.vertices()
        )

        if vertices:

            primeiro = vertices[0]
            ultimo = vertices[-1]

            partes.extend([

                "X1=" +
                normalizar_valor(
                    primeiro.x()
                ),

                "Y1=" +
                normalizar_valor(
                    primeiro.y()
                ),

                "X2=" +
                normalizar_valor(
                    ultimo.x()
                ),

                "Y2=" +
                normalizar_valor(
                    ultimo.y()
                )

            ])

    except Exception:
        pass


    texto = ";".join(
        partes
    )


    return hashlib.sha1(
        texto.encode("utf-8")
    ).hexdigest()[:TAMANHO_HASH]


# ============================================================
# HASH DA CLASSIFICAÇÃO
# ============================================================

def criar_hash_classificacao(
    nome_centroide,
    nome_destino,
    centroide,
    poligono
):

    partes = [

        nome_centroide,

        nome_destino,

        hash_geometria(
            poligono.geometry()
        )

    ]


    for campo in centroide.fields():

        partes.append(
            campo.name()
            + "="
            + normalizar_valor(
                centroide[
                    campo.name()
                ]
            )
        )


    texto = "||".join(
        partes
    )


    return hashlib.sha1(
        texto.encode("utf-8")
    ).hexdigest()[:TAMANHO_HASH]


# ============================================================
# CONEXÃO POSTGIS
# ============================================================

def obter_conexao_postgis(camada):

    if camada.providerType() != "postgres":

        return None

    try:

        uri = QgsDataSourceUri(
            camada.source()
        )

        metadata = (
            QgsProviderRegistry
            .instance()
            .providerMetadata(
                "postgres"
            )
        )

        if metadata is None:
            return None

        conexao = metadata.createConnection(
            uri.connectionInfo(True),
            {}
        )

        return conexao

    except Exception as e:

        print(
            "ERRO ao abrir conexão PostGIS:",
            e
        )

        return None


# ============================================================
# CONSULTAR RESTRIÇÕES REAIS DO POSTGRESQL
# ============================================================

def obter_restricoes_postgis(camada):

    resultado = {}


    if camada.providerType() != "postgres":

        print(
            "ATENÇÃO:",
            camada.name(),
            "não é uma camada PostGIS."
        )

        return resultado


    uri = QgsDataSourceUri(
        camada.source()
    )

    schema = uri.schema()
    tabela = uri.table()


    conexao = obter_conexao_postgis(
        camada
    )


    if conexao is None:

        return resultado


    schema_sql = schema.replace(
        "'",
        "''"
    )

    tabela_sql = tabela.replace(
        "'",
        "''"
    )


    sql = f"""
        SELECT
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = '{schema_sql}'
          AND table_name = '{tabela_sql}'
        ORDER BY ordinal_position
    """


    try:

        linhas = conexao.executeSql(
            sql
        )

    except Exception as e:

        print(
            "ERRO CONSULTANDO RESTRIÇÕES:",
            camada.name()
        )

        print(e)

        return resultado


    for linha in linhas:

        if len(linha) < 5:
            continue


        nome = str(linha[0])

        tipo = str(linha[1])

        udt = str(linha[2])

        nullable = str(linha[3])

        default = linha[4]


        resultado[nome] = {

            "tipo": tipo,

            "udt": udt,

            "nullable": nullable,

            "not_null":
                nullable.upper() == "NO",

            "default":
                default,

        }


    return resultado


# ============================================================
# MOSTRAR RESTRIÇÕES
# ============================================================

def mostrar_restricoes(
    camada,
    restricoes
):

    print("")
    print(
        "----------------------------------------------"
    )

    print(
        "RESTRIÇÕES:",
        camada.name()
    )

    for nome, info in restricoes.items():

        if info["not_null"]:

            if info["default"]:

                print(
                    "  NOT NULL + DEFAULT:",
                    nome,
                    "=",
                    info["default"]
                )

            else:

                print(
                    "  NOT NULL SEM DEFAULT:",
                    nome
                )

    print(
        "----------------------------------------------"
    )


# ============================================================
# VALOR PADRÃO PELO TIPO
# ============================================================

def valor_padrao_tipo(
    info,
    campo_qgis
):

    tipo = str(
        info.get(
            "udt",
            ""
        )
    ).lower()


    tipo_qgis = (
        campo_qgis
        .typeName()
        .lower()
    )


    # --------------------------------------------------------
    # BOOLEAN
    # --------------------------------------------------------

    if (
        tipo in (
            "bool",
            "boolean"
        )
        or "bool" in tipo_qgis
    ):

        return VALORES_PADRAO[
            "booleano"
        ]


    # --------------------------------------------------------
    # NUMÉRICO
    # --------------------------------------------------------

    if (
        tipo in (
            "int2",
            "int4",
            "int8",
            "float4",
            "float8",
            "numeric",
            "decimal"
        )
        or "int" in tipo_qgis
        or "numeric" in tipo_qgis
        or "double" in tipo_qgis
        or "float" in tipo_qgis
    ):

        return VALORES_PADRAO[
            "numerico"
        ]


    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    return VALORES_PADRAO[
        "texto"
    ]


# ============================================================
# INTERPRETAR DEFAULT DO POSTGRES
# ============================================================

def interpretar_default(
    default_sql,
    info,
    campo
):

    if default_sql is None:

        return (
            valor_padrao_tipo(
                info,
                campo
            )
        )


    texto = str(
        default_sql
    ).strip()


    texto_lower = texto.lower()


    # --------------------------------------------------------
    # DEFAULT GERADO PELO BANCO
    #
    # Nestes casos deixamos o banco resolver.
    # --------------------------------------------------------

    if (
        "current_timestamp"
        in texto_lower
        or "current_date"
        in texto_lower
        or "now()"
        in texto_lower
        or "nextval("
        in texto_lower
        or "uuid_generate"
        in texto_lower
        or "gen_random_uuid"
        in texto_lower
    ):

        return None


    # --------------------------------------------------------
    # BOOLEAN
    # --------------------------------------------------------

    if texto_lower in (
        "true",
        "false"
    ):

        return (
            texto_lower == "true"
        )


    # --------------------------------------------------------
    # NÚMERO
    # --------------------------------------------------------

    numero = texto.replace(
        "'",
        ""
    ).strip()


    try:

        if (
            "." in numero
        ):

            return float(
                numero
            )

        return int(
            numero
        )

    except Exception:
        pass


    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    if (
        texto.startswith("'")
        and texto.endswith("'")
    ):

        return texto[
            1:-1
        ]


    # --------------------------------------------------------
    # CASO DESCONHECIDO
    # --------------------------------------------------------

    return (
        valor_padrao_tipo(
            info,
            campo
        )
    )


# ============================================================
# PREPARAR ATRIBUTOS
# ============================================================

def preparar_atributos(
    centroide,
    poligono,
    camada_centroide,
    camada_poligonos,
    camada_destino,
    restricoes
):

    campos_centroide = (
        camada_centroide.fields()
    )

    campos_poligono = (
        camada_poligonos.fields()
    )

    campos_destino = (
        camada_destino.fields()
    )


    valores = []


    for campo_destino in campos_destino:

        nome_campo = (
            campo_destino.name()
        )


        valor = None


        # ====================================================
        # 1. ATRIBUTO DO CENTROIDE
        # ====================================================

        indice = (
            campos_centroide.indexOf(
                nome_campo
            )
        )


        if indice >= 0:

            valor = centroide[
                indice
            ]


        # ====================================================
        # 2. ATRIBUTO DO POLÍGONO
        # ====================================================

        if (
            valor is None
            or valor is NULL
        ):

            indice = (
                campos_poligono.indexOf(
                    nome_campo
                )
            )


            if indice >= 0:

                valor = poligono[
                    indice
                ]


        # ====================================================
        # 3. VERIFICAR POSTGIS
        # ====================================================

        if (
            valor is None
            or valor is NULL
        ):

            info = (
                restricoes.get(
                    nome_campo
                )
            )


            if (
                info is not None
                and info["not_null"]
            ):

                default_sql = (
                    info["default"]
                )


                # --------------------------------------------
                # Existe DEFAULT
                # --------------------------------------------

                if (
                    default_sql is not None
                    and str(
                        default_sql
                    ).strip() != ""
                ):

                    valor = (
                        interpretar_default(
                            default_sql,
                            info,
                            campo_destino
                        )
                    )


                # --------------------------------------------
                # NOT NULL sem DEFAULT
                # --------------------------------------------

                else:

                    valor = (
                        valor_padrao_tipo(
                            info,
                            campo_destino
                        )
                    )


        valores.append(
            valor
        )


    return valores


# ============================================================
# LOCALIZAR CAMADA DE POLÍGONOS
# ============================================================

def encontrar_camada_poligonos():
    # 1. Tenta pelo nome exato configurado
    c = encontrar_camada(NOME_CAMADA_POLIGONOS)
    if c is not None and c.geometryType() == QgsWkbTypes.PolygonGeometry:
        return c
    # 2. Tenta qualquer camada vetorial de polígono que contenha 'poligono'
    for camada in projeto.mapLayers().values():
        if not isinstance(camada, QgsVectorLayer):
            continue
        if camada.geometryType() == QgsWkbTypes.PolygonGeometry:
            norm = normalizar_nome(camada.name())
            if "poligono" in norm:
                return camada
    return None

camada_poligonos = encontrar_camada_poligonos()


if camada_poligonos is None:

    raise Exception(
        "A camada de polígonos ('"
        + NOME_CAMADA_POLIGONOS
        + "') não foi encontrada no projeto."
    )


# ============================================================
# LIMPAR CAMADAS TEMPORÁRIAS ANTERIORES DO PROJETO
# ============================================================

for camada in list(projeto.mapLayers().values()):
    if isinstance(camada, QgsVectorLayer):
        nome_camada = camada.name()
        if (nome_camada.startswith(PREFIXO_TEMP)
                or nome_camada in (NOME_CAMADA_NAO_CLASSIFICADAS, "areas_nao_classificadas")):
            projeto.removeMapLayer(camada.id())


# ============================================================
# LOCALIZAR CAMADAS DE CENTROIDES
# REGRA: APENAS camadas que comecem com 'centroide_' e terminem com '_p' (centroide_[nome]_p)
# ============================================================

def obter_todas_camadas_centroides():
    camadas_encontradas = {}

    for camada in projeto.mapLayers().values():
        if not isinstance(camada, QgsVectorLayer):
            continue
        if camada.geometryType() != QgsWkbTypes.PointGeometry:
            continue

        norm = normalizar_nome(camada.name())

        # REGRA ESTRITA: deve começar com 'centroide_' e terminar com '_p'
        if not (norm.startswith("centroide_") and norm.endswith("_p")):
            continue

        nome_extraido = norm[len("centroide_") : -len("_p")].strip("_")
        if not nome_extraido:
            continue

        chave = identificar_classe(nome_extraido)
        if chave is None:
            chave = nome_extraido

        if chave not in CONFIG_CLASSES:
            rotulo = chave.replace("_", " ").title()
            tipo = "sobreposicao" if chave in ("ilha", "ocupacao_solo") else "base"
            CONFIG_CLASSES[chave] = {
                "rotulo": rotulo,
                "tipo_classe": tipo,
                "palavras_chave": [chave],
                "nomes_possiveis_destino": [
                    f"cobter_{chave}_a",
                    f"elemnat_{chave}_a",
                    f"aux_{chave}_a",
                    f"{chave}_a"
                ],
                "nome_padrao_destino": f"cobter_{chave}_a",
                "nome_temp": f"{PREFIXO_TEMP}cobter_{chave}_a"
            }

        camadas_encontradas[chave] = camada

    return camadas_encontradas


centroides_por_classe = obter_todas_camadas_centroides()

print("")
print("==============================================")
print("CAMADAS DE CENTROIDES ENCONTRADAS")
print("==============================================")
for chave, camada in centroides_por_classe.items():
    print(f"  [{CONFIG_CLASSES[chave]['rotulo']}]: {camada.name()} ({camada.featureCount()} feições)")

if not centroides_por_classe:
    raise Exception("Nenhuma camada de centroide (centroide_*_p) foi encontrada no projeto.")


# ============================================================
# LOCALIZAR CAMADAS MODELO / DESTINO
# ============================================================

def encontrar_camada_destino_modelo(chave):
    config = CONFIG_CLASSES[chave]
    nomes_candidatos = config.get("nomes_possiveis_destino", [config["nome_padrao_destino"]])

    # 1. Procurar nas camadas abertas no QGIS por nome exato ou normalizado
    for nome_cand in nomes_candidatos:
        c = encontrar_camada(nome_cand)
        if c is not None and c.geometryType() == QgsWkbTypes.PolygonGeometry:
            return c

    # 2. Procurar qualquer camada de polígono que corresponda à classe
    for camada in projeto.mapLayers().values():
        if not isinstance(camada, QgsVectorLayer) or camada.geometryType() != QgsWkbTypes.PolygonGeometry:
            continue
        norm = normalizar_nome(camada.name())
        if "poligono" in norm or norm.startswith("temp_") or norm == NOME_CAMADA_NAO_CLASSIFICADAS:
            continue
        if identificar_classe(camada.name()) == chave:
            return camada

    return None


modelos_destino = {}
for chave in centroides_por_classe:
    modelos_destino[chave] = encontrar_camada_destino_modelo(chave)


# ============================================================
# CONSULTAR RESTRIÇÕES POSTGIS
# ============================================================

restricoes_destino = {}

print("")
print("==============================================")
print("CONSULTANDO RESTRIÇÕES POSTGIS")
print("==============================================")

for chave, camada_destino in modelos_destino.items():
    if camada_destino is not None:
        restricoes = obter_restricoes_postgis(camada_destino)
        restricoes_destino[chave] = restricoes
        mostrar_restricoes(camada_destino, restricoes)
    else:
        restricoes_destino[chave] = {}


# ============================================================
# CRIAR CAMADAS TEMPORÁRIAS EM MEMÓRIA
# ============================================================

camadas_temp = {}

if GERAR_CAMADA_TEMPORARIA:
    print("")
    print("==============================================")
    print("CRIANDO CAMADAS TEMPORÁRIAS EM MEMÓRIA")
    print("==============================================")

    for chave in centroides_por_classe:
        config = CONFIG_CLASSES[chave]
        camada_destino = modelos_destino.get(chave)
        nome_camada_temp = f"{PREFIXO_TEMP}{camada_destino.name()}" if camada_destino is not None else config["nome_temp"]

        # Se já existir camada temporária com esse nome no projeto, remove
        camada_existente = encontrar_camada(nome_camada_temp)
        if camada_existente is not None:
            projeto.removeMapLayer(camada_existente.id())

        crs = camada_destino.crs() if camada_destino is not None else camada_poligonos.crs()
        tipo_wkb = camada_destino.wkbType() if camada_destino is not None else camada_poligonos.wkbType()
        tipo_geom = "MultiPolygon" if QgsWkbTypes.isMultiType(tipo_wkb) else "Polygon"

        camada_temp = QgsVectorLayer(
            f"{tipo_geom}?crs={crs.authid()}",
            nome_camada_temp,
            "memory"
        )
        pr = camada_temp.dataProvider()

        if camada_destino is not None:
            campos_modelo = camada_destino.fields()
        else:
            campos_modelo = camada_poligonos.fields()

        novos_campos = [
            QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision())
            for f in campos_modelo
        ]
        pr.addAttributes(novos_campos)
        camada_temp.updateFields()

        camadas_temp[chave] = camada_temp
        print(f"Camada temporária criada: {nome_camada_temp} ({tipo_geom})")


# ============================================================
# INDEXAR CENTROIDES ESPACIALMENTE
# ============================================================

indices_centroides = {}
mapa_centroides = {}

print("")
print("==============================================")
print("INDEXANDO CENTROIDES ESPACIALMENTE")
print("==============================================")

for chave, camada_centroide in centroides_por_classe.items():
    idx = QgsSpatialIndex()
    mapa = {}

    transformador = None
    if camada_centroide.crs() != camada_poligonos.crs():
        transformador = QgsCoordinateTransform(
            camada_centroide.crs(),
            camada_poligonos.crs(),
            projeto
        )
        print(f"  [CRS] Reprojetando {camada_centroide.name()} ({camada_centroide.crs().authid()} -> {camada_poligonos.crs().authid()})")

    for feicao in camada_centroide.getFeatures():
        geom = feicao.geometry()
        if geom is None or geom.isEmpty():
            continue

        if transformador is not None:
            geom_trans = QgsGeometry(geom)
            geom_trans.transform(transformador)
        else:
            geom_trans = geom

        f_aux = QgsFeature()
        f_aux.setId(feicao.id())
        f_aux.setGeometry(geom_trans)
        idx.addFeature(f_aux)
        mapa[feicao.id()] = (feicao, geom_trans)

    indices_centroides[chave] = idx
    mapa_centroides[chave] = mapa
    print(f"  [{CONFIG_CLASSES[chave]['rotulo']}]: {len(mapa)} centroides indexados")


# ============================================================
# LOCALIZAR PRIMEIRO CENTROIDE DENTRO DO POLÍGONO
# ============================================================

def encontrar_primeiro_centroide_na_area(geom_poligono, chave):
    if geom_poligono is None or geom_poligono.isEmpty():
        return None

    idx = indices_centroides.get(chave)
    mapa = mapa_centroides.get(chave)
    if idx is None or mapa is None:
        return None

    bbox = geom_poligono.boundingBox()
    candidatos = list(idx.intersects(bbox))

    if not candidatos:
        return None

    # Consulta espacial pura: o ponto do centroide precisa estar CONTIDO ou TOCANDO o polígono
    for cid in candidatos:
        item = mapa.get(cid)
        if item is None:
            continue
        feicao_orig, geom_pt = item
        # Predicado espacial exato (sem distância/buffer): ST_Contains / ST_Intersects
        if geom_poligono.contains(geom_pt) or geom_poligono.intersects(geom_pt):
            return feicao_orig

    return None


# ============================================================
# INSERIR POLÍGONO CLASSIFICADO NA CAMADA DE DESTINO
# ============================================================

def inserir_poligono_no_alvo(
    camada_alvo,
    poly,
    feicao_centroide,
    camada_centroide,
    camada_poligonos,
    restricoes
):
    nova_feicao = QgsFeature(camada_alvo.fields())
    geom_final = QgsGeometry(poly.geometry())
    if (
        QgsWkbTypes.isMultiType(camada_alvo.wkbType())
        and not geom_final.isMultipart()
    ):
        geom_final.convertToMultiType()
    nova_feicao.setGeometry(geom_final)

    try:
        valores = preparar_atributos(
            feicao_centroide,
            poly,
            camada_centroide,
            camada_poligonos,
            camada_alvo,
            restricoes
        )
        nova_feicao.setAttributes(valores)
    except Exception as e:
        msg_erro = f"Erro preparando atributos ({camada_alvo.name()}): {e}"
        print(f"ERRO PREPARANDO ATRIBUTOS ({camada_alvo.name()}): {e}")
        return False, msg_erro

    try:
        sucesso, erros = camada_alvo.dataProvider().addFeatures([nova_feicao])
        if not sucesso:
            msg_erro = f"Falha ao gravar feição em {camada_alvo.name()}: {erros}"
            print(f"ERRO AO INSERIR em {camada_alvo.name()}: {erros}")
            return False, msg_erro
        return True, ""
    except Exception as e:
        msg_erro = f"Exceção ao inserir em {camada_alvo.name()}: {e}"
        print(f"ERRO AO INSERIR em {camada_alvo.name()}: {e}")
        return False, msg_erro


# ============================================================
# CONTADORES E DEDUPLICAÇÃO
# ============================================================

hashes_geometria = {chave: set() for chave in centroides_por_classe}

if not GERAR_CAMADA_TEMPORARIA:
    print("")
    print("==============================================")
    print("INDEXANDO FEIÇÕES EXISTENTES DO BANCO")
    print("==============================================")
    for chave, camada_destino in modelos_destino.items():
        if camada_destino is not None:
            for feicao in camada_destino.getFeatures():
                geom = feicao.geometry()
                if geom is not None and not geom.isEmpty():
                    hashes_geometria[chave].add(hash_geometria(geom))
            print(f"  {CONFIG_CLASSES[chave]['rotulo']} -> {len(hashes_geometria[chave])} feições no banco")

total_poligonos_analisados = 0
total_com_poligono = 0
total_inseridos = 0
total_duplicados = 0
total_erros = 0
erros_detalhados = []

poligonos_classificados_ids = set()
poligonos_sem_centroide = []  # Lista de tuplas: (feicao_poly, motivo_str)

classes_base = [
    chave for chave, cfg in CONFIG_CLASSES.items()
    if cfg.get("tipo_classe", "base") == "base" and chave in centroides_por_classe
]

classes_sobreposicao = [
    chave for chave, cfg in CONFIG_CLASSES.items()
    if cfg.get("tipo_classe", "base") == "sobreposicao" and chave in centroides_por_classe
]

total_trabalho = camada_poligonos.featureCount()
if total_trabalho <= 0:
    total_trabalho = 1

janela_pai = iface.mainWindow() if iface is not None else None

dialog_progresso = None
if QProgressDialog is not None:
    dialog_progresso = QProgressDialog(
        "Classificando feições da camada Polígonos...",
        "Cancelar",
        0,
        total_trabalho,
        janela_pai
    )
    dialog_progresso.setWindowTitle("Classificação de Polígonos")
    dialog_progresso.setWindowModality(
        Qt.WindowModal if (Qt is not None and hasattr(Qt, "WindowModal")) else 1
    )
    dialog_progresso.setMinimumDuration(0)
    dialog_progresso.setValue(0)
    if QApplication is not None:
        QApplication.processEvents()

progresso_atual = 0
cancelado_pelo_usuario = False
inicio_geral = time.time()

print("")
print("==============================================")
print(f"INICIANDO CLASSIFICAÇÃO: {total_trabalho} POLÍGONOS")
print("==============================================")


# ============================================================
# ITERAR POR TODAS AS FEIÇÕES DA CAMADA POLÍGONOS
# ============================================================

for poly in camada_poligonos.getFeatures():

    if dialog_progresso is not None and dialog_progresso.wasCanceled():
        cancelado_pelo_usuario = True
        print("Processamento cancelado pelo usuário.")
        break

    total_poligonos_analisados += 1
    progresso_atual += 1

    if dialog_progresso is not None and (
        progresso_atual % 10 == 0
        or progresso_atual == total_trabalho
    ):
        dialog_progresso.setValue(progresso_atual)
        dialog_progresso.setLabelText(
            f"Classificando polígono: {progresso_atual}/{total_trabalho}"
        )
        if QApplication is not None:
            QApplication.processEvents()

    geom_poly = poly.geometry()
    if geom_poly is None or geom_poly.isEmpty():
        total_erros += 1
        poligonos_sem_centroide.append((poly, "Geometria nula ou vazia"))
        continue

    # Garantir validade topológica para GEOS contains/intersects
    geom_poly_consulta = geom_poly
    try:
        if not geom_poly.isGeosValid():
            geom_valida = geom_poly.makeValid()
            if geom_valida is not None and not geom_valida.isEmpty():
                geom_poly_consulta = geom_valida
    except Exception:
        pass

    classificado_neste_poligono = False
    motivo_falha = "Sem centroide correspondente"

    # --------------------------------------------------------
    # 1. COBERTURA TERRESTRE (BASE)
    # Pega o primeiro centroide correspondente que encontrar
    # --------------------------------------------------------
    for chave in classes_base:
        feicao_centroide = encontrar_primeiro_centroide_na_area(geom_poly_consulta, chave)
        if feicao_centroide is not None:
            camada_alvo = camadas_temp[chave] if GERAR_CAMADA_TEMPORARIA else modelos_destino.get(chave)
            if camada_alvo is None:
                continue

            camada_orig_centroide = centroides_por_classe[chave]
            restricoes = restricoes_destino.get(chave, {})

            # No modo banco, checar se polígono idêntico já existe no banco
            if not GERAR_CAMADA_TEMPORARIA:
                hash_geom = hash_geometria(geom_poly)
                if hash_geom in hashes_geometria[chave]:
                    total_duplicados += 1
                    classificado_neste_poligono = True
                    break

            sucesso, msg_erro = inserir_poligono_no_alvo(
                camada_alvo,
                poly,
                feicao_centroide,
                camada_orig_centroide,
                camada_poligonos,
                restricoes
            )
            if sucesso:
                if not GERAR_CAMADA_TEMPORARIA:
                    hashes_geometria[chave].add(hash_geom)
                total_inseridos += 1
                classificado_neste_poligono = True
                break
            else:
                total_erros += 1
                motivo_falha = f"Erro ao inserir em {camada_alvo.name()}: {msg_erro}"
                erros_detalhados.append(f"Polígono {poly.id()}: {motivo_falha}")
                break

    # --------------------------------------------------------
    # 2. SOBREPOSIÇÃO (ILHA, OCUPAÇÃO DO SOLO)
    # Se houver centroide de ilha ou ocupação, grava também nessa camada
    # --------------------------------------------------------
    for chave in classes_sobreposicao:
        feicao_centroide = encontrar_primeiro_centroide_na_area(geom_poly_consulta, chave)
        if feicao_centroide is not None:
            camada_alvo = camadas_temp[chave] if GERAR_CAMADA_TEMPORARIA else modelos_destino.get(chave)
            if camada_alvo is None:
                continue

            camada_orig_centroide = centroides_por_classe[chave]
            restricoes = restricoes_destino.get(chave, {})

            if not GERAR_CAMADA_TEMPORARIA:
                hash_geom = hash_geometria(geom_poly)
                if hash_geom in hashes_geometria[chave]:
                    total_duplicados += 1
                    classificado_neste_poligono = True
                    continue

            sucesso, msg_erro = inserir_poligono_no_alvo(
                camada_alvo,
                poly,
                feicao_centroide,
                camada_orig_centroide,
                camada_poligonos,
                restricoes
            )
            if sucesso:
                if not GERAR_CAMADA_TEMPORARIA:
                    hashes_geometria[chave].add(hash_geom)
                total_inseridos += 1
                classificado_neste_poligono = True
            else:
                total_erros += 1
                if not classificado_neste_poligono:
                    motivo_falha = f"Erro ao inserir em {camada_alvo.name()}: {msg_erro}"
                erros_detalhados.append(f"Polígono {poly.id()}: {msg_erro}")

    if classificado_neste_poligono:
        total_com_poligono += 1
        poligonos_classificados_ids.add(poly.id())
    else:
        poligonos_sem_centroide.append((poly, motivo_falha))

if dialog_progresso is not None:
    dialog_progresso.setValue(total_trabalho)
    dialog_progresso.close()


# ============================================================
# POLÍGONOS NÃO CLASSIFICADOS (FLAGS)
# ============================================================

total_nao_classificados = len(poligonos_sem_centroide)
camada_nao_classif = None

# Remover camada de flags anterior do projeto se existir
camada_flags_antiga = encontrar_camada(NOME_CAMADA_NAO_CLASSIFICADAS)
if camada_flags_antiga is not None:
    projeto.removeMapLayer(camada_flags_antiga.id())

if poligonos_sem_centroide:
    crs_poly = camada_poligonos.crs()
    tipo_wkb = camada_poligonos.wkbType()
    tipo_geom = (
        "MultiPolygon"
        if QgsWkbTypes.isMultiType(tipo_wkb)
        else "Polygon"
    )

    camada_nao_classif = QgsVectorLayer(
        f"{tipo_geom}?crs={crs_poly.authid()}",
        NOME_CAMADA_NAO_CLASSIFICADAS,
        "memory"
    )

    pr_nc = camada_nao_classif.dataProvider()

    campos_nc = [
        QgsField(
            f.name(),
            f.type(),
            f.typeName(),
            f.length(),
            f.precision()
        )
        for f in camada_poligonos.fields()
    ]

    nomes_existentes = [f.name().lower() for f in campos_nc]
    if "motivo" not in nomes_existentes:
        campos_nc.append(QgsField("motivo", 10, "text", 100, 0))

    pr_nc.addAttributes(campos_nc)
    camada_nao_classif.updateFields()

    novas_flags = []
    for poly, motivo in poligonos_sem_centroide:
        f_nc = QgsFeature(camada_nao_classif.fields())
        geom_f = QgsGeometry(poly.geometry())
        if (
            QgsWkbTypes.isMultiType(camada_nao_classif.wkbType())
            and not geom_f.isMultipart()
        ):
            geom_f.convertToMultiType()

        f_nc.setGeometry(geom_f)

        vals = []
        for c in camada_nao_classif.fields():
            n = c.name()
            if n == "motivo":
                vals.append(motivo)
            else:
                idx_orig = camada_poligonos.fields().indexOf(n)
                vals.append(poly[idx_orig] if idx_orig >= 0 else None)

        f_nc.setAttributes(vals)
        novas_flags.append(f_nc)

    pr_nc.addFeatures(novas_flags)
    camada_nao_classif.updateExtents()

    # Estilo visual de alerta para flags (vermelho semi-transparente)
    try:
        from qgis.core import QgsFillSymbol
        simbolo = QgsFillSymbol.createSimple({
            'color': '255,0,0,60',
            'color_border': 'red',
            'width_border': '0.7',
            'style': 'solid'
        })
        camada_nao_classif.renderer().setSymbol(simbolo)
    except Exception:
        pass

    print("")
    print("==============================================")
    print(f"FLAGS: {total_nao_classificados} polígonos sem centroide na camada '{NOME_CAMADA_NAO_CLASSIFICADAS}'")
    print("==============================================")

else:
    print("")
    print("==============================================")
    print("FLAGS: Todos os polígonos possuem centroide correspondente (0 flags geradas)!")
    print("==============================================")


# ============================================================
# ORGANIZAR EM GRUPO NO QGIS: Areas_cobertura_terrestre
# ============================================================

raiz = projeto.layerTreeRoot()
grupo = raiz.findGroup(NOME_GRUPO)
if grupo is None:
    grupo = raiz.addGroup(NOME_GRUPO)

if GERAR_CAMADA_TEMPORARIA:

    print("")
    print("==============================================")
    print(f"ORGANIZANDO CAMADAS NO GRUPO: '{NOME_GRUPO}'")
    print("==============================================")

    # Ordem de baixo para cima:
    # 1. area_edificada (fundo)
    # 2. massa_dagua
    # 3. vegetacao
    # 4. terreno_exposto
    # 5. outras bases
    # 6. ocupacao_solo
    # 7. ilha
    # 8. areas_nao_classificadas (topo absoluto)
    ordem_chaves = ["area_edificada", "massa_dagua", "vegetacao", "terreno_exposto"]
    for k in centroides_por_classe:
        if k not in ordem_chaves and k not in ("ocupacao_solo", "ilha"):
            ordem_chaves.append(k)
    ordem_chaves.extend(["ocupacao_solo", "ilha"])

    for chave in ordem_chaves:
        c_temp = camadas_temp.get(chave)
        if c_temp is not None and c_temp.featureCount() > 0:
            c_temp.updateExtents()
            if projeto.mapLayer(c_temp.id()) is None:
                projeto.addMapLayer(c_temp, False)
            if grupo.findLayer(c_temp.id()) is None:
                grupo.insertLayer(0, c_temp)
            print(f"  -> {c_temp.name()} ({c_temp.featureCount()} polígonos) inserida no grupo '{NOME_GRUPO}'")

    if camada_nao_classif is not None and camada_nao_classif.featureCount() > 0:
        if projeto.mapLayer(camada_nao_classif.id()) is None:
            projeto.addMapLayer(camada_nao_classif, False)
        if grupo.findLayer(camada_nao_classif.id()) is None:
            grupo.insertLayer(0, camada_nao_classif)
        print(f"  -> {camada_nao_classif.name()} ({camada_nao_classif.featureCount()} flags) inserida no topo do grupo '{NOME_GRUPO}'")

else:

    for chave, c_dest in modelos_destino.items():
        if c_dest is not None:
            try:
                c_dest.updateExtents()
            except Exception:
                pass


# ============================================================
# ATUALIZAR CAMADAS
# ============================================================

camadas_repintar = (
    [c for c in camadas_temp.values() if c.featureCount() > 0]
    if GERAR_CAMADA_TEMPORARIA
    else [c for c in modelos_destino.values() if c is not None]
)

if camada_nao_classif is not None:
    camadas_repintar.append(camada_nao_classif)

for camada in camadas_repintar:
    if camada is not None:
        try:
            camada.triggerRepaint()
        except Exception:
            pass


# ============================================================
# TEMPO TOTAL
# ============================================================

tempo_total = (
    time.time()
    - inicio_geral
)


# ============================================================
# RESULTADO FINAL
# ============================================================

print("")
print("")
print(
    "================================================"
)
print(
    "       PROCESSAMENTO FINALIZADO"
)
print(
    "================================================"
)
print("")

if GERAR_CAMADA_TEMPORARIA:
    print("MODO: Camadas Temporárias (NÃO gravado no banco)")
    print("Camadas geradas no QGIS:")
    for nome_dest, c_temp in camadas_temp.items():
        if c_temp.featureCount() > 0:
            print(f"  - {c_temp.name()}: {c_temp.featureCount()} polígonos")
    print("")
else:
    print("MODO: Gravação direta no banco PostGIS")
    print("")

print("Polígonos analisados (camada Polígonos):", total_poligonos_analisados)
print("Polígonos com centroide:", total_com_poligono)
print("Novos polígonos criados:", total_inseridos)
print("Duplicados evitados:", total_duplicados)
print("Polígonos sem centroide (flags):", total_nao_classificados)
print("Erros:", total_erros)
print("Tempo total:", round(tempo_total, 2), "segundos")
print("")
print(
    "================================================"
)


# ============================================================
# DIALOG E ALERTA FINAL (INTERFACE QGIS)
# ============================================================

lista_camadas_criadas_html = ""
if GERAR_CAMADA_TEMPORARIA:
    for chave, c_temp in camadas_temp.items():
        if c_temp.featureCount() > 0:
            lista_camadas_criadas_html += (
                f"<li><b>{c_temp.name()}</b> ({CONFIG_CLASSES[chave]['rotulo']}): {c_temp.featureCount()} polígono(s)</li>"
            )
else:
    for chave, c_dest in modelos_destino.items():
        if c_dest is not None:
            lista_camadas_criadas_html += (
                f"<li><b>{c_dest.name()}</b> ({CONFIG_CLASSES[chave]['rotulo']} - PostGIS)</li>"
            )

# Destaque quando não tiver / quando tiver áreas sem centroide
if total_nao_classificados == 0:
    destaque_flags_html = f"""
    <div style='background-color: #e8f8f5; border: 2px solid #27ae60; border-radius: 8px; padding: 12px; margin: 12px 0;'>
        <h3 style='color: #1e8449; margin: 0 0 6px 0;'>🎉 SUCESSO: NENHUMA ÁREA SEM CENTROIDE!</h3>
        <p style='color: #145a32; margin: 0; font-size: 13px; line-height: 1.4;'>
            <b>100% dos polígonos foram classificados com sucesso!</b> (Total: {total_poligonos_analisados} polígonos)<br>
            A soma das feições geradas é <b>{total_inseridos}</b> (incluindo possíveis sobreposições de ilha/ocupação).<br>
            Não há áreas sem centroide pendentes.
        </p>
    </div>
    """
else:
    destaque_flags_html = f"""
    <div style='background-color: #fdf2e9; border: 2px solid #e67e22; border-radius: 8px; padding: 12px; margin: 12px 0;'>
        <h3 style='color: #d35400; margin: 0 0 6px 0;'>⚠️ ATENÇÃO: POLÍGONOS SEM CENTROIDE ENCONTRADOS!</h3>
        <p style='color: #7e5109; margin: 0; font-size: 13px; line-height: 1.4;'>
            Foram encontrados <b>{total_nao_classificados}</b> polígono(s) <b>sem centroide correspondente</b> (de {total_poligonos_analisados} analisados).<br>
            Eles foram adicionados à camada <b>'{NOME_CAMADA_NAO_CLASSIFICADAS}'</b> (destacada em vermelho) para você ajustar e rodar novamente até zerar as flags.
        </p>
    </div>
    """

if lista_camadas_criadas_html:
    secao_camadas_html = f"""
    <p style='margin-bottom: 4px;'><b>Camadas geradas no grupo '{NOME_GRUPO}':</b></p>
    <ul style='margin-top: 4px;'>{lista_camadas_criadas_html}</ul>
    """
else:
    secao_camadas_html = "<p>Nenhuma nova feição foi gerada nas camadas de destino.</p>"

secao_erros_html = ""
if total_erros > 0:
    detalhes_li = "".join([f"<li>{e}</li>" for e in erros_detalhados[:5]])
    if len(erros_detalhados) > 5:
        detalhes_li += f"<li>... e mais {len(erros_detalhados) - 5} erro(s).</li>"
    secao_erros_html = f"""
    <div style='background-color: #fceae9; border: 1px solid #e74c3c; border-radius: 6px; padding: 8px; margin-top: 8px;'>
        <p style='color: #c0392b; margin: 0 0 4px 0;'><b>Erros encontrados ({total_erros}):</b></p>
        <ul style='color: #962d22; font-size: 11px; margin: 0; padding-left: 18px;'>{detalhes_li}</ul>
    </div>
    """

resumo_html = f"""
<hr style='border: none; border-top: 1px solid #ddd; margin: 10px 0;'>
<table style='font-size: 12px; color: #444; width: 100%;'>
    <tr><td><b>Polígonos analisados:</b></td><td align='right'>{total_poligonos_analisados}</td></tr>
    <tr><td><b>Polígonos com centroide:</b></td><td align='right'>{total_com_poligono}</td></tr>
    <tr><td><b>Total de feições criadas:</b></td><td align='right'>{total_inseridos}</td></tr>
    <tr><td><b>Duplicados evitados:</b></td><td align='right'>{total_duplicados}</td></tr>
    <tr><td><b>Polígonos sem centroide (flags):</b></td><td align='right'>{total_nao_classificados}</td></tr>
    <tr><td><b>Erros de inserção/geometria:</b></td><td align='right' style='color: {"#e74c3c" if total_erros > 0 else "#444"};'><b>{total_erros}</b></td></tr>
    <tr><td><b>Tempo total:</b></td><td align='right'>{round(tempo_total, 2)}s</td></tr>
</table>
{secao_erros_html}
"""

mensagem_html = f"""
<div style='min-width: 380px;'>
    <h2 style='margin-top: 0; color: #2c3e50;'>Classificação de Polígonos Concluída</h2>
    {destaque_flags_html}
    {secao_camadas_html}
    {resumo_html}
</div>
"""

if QMessageBox is not None:
    msg_box = QMessageBox(janela_pai)
    msg_box.setWindowTitle("Classificação de Polígonos")
    if total_nao_classificados == 0:
        msg_box.setIcon(QMessageBox.Information)
    else:
        msg_box.setIcon(QMessageBox.Warning)
    msg_box.setTextFormat(
        Qt.RichText if (Qt is not None and hasattr(Qt, "RichText")) else 1
    )
    msg_box.setText(mensagem_html)
    msg_box.exec_()

if iface is not None:
    if total_nao_classificados == 0:
        iface.messageBar().pushSuccess(
            "Classificação Concluída",
            f"Camadas criadas com sucesso no grupo '{NOME_GRUPO}'! 100% dos {total_poligonos_analisados} polígonos possuem centroide (0 flags)."
        )
    else:
        iface.messageBar().pushWarning(
            "Classificação Concluída",
            f"Camadas criadas! {total_nao_classificados} polígonos sem centroide na camada '{NOME_CAMADA_NAO_CLASSIFICADAS}'."
        )
